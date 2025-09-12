import math
import numpy as np
from pathlib import Path
import os
import numpy as np
import csv
import time

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
STATE_PATH = DATA_DIR / "reinforce_state.npz"
LOG_PATH   = DATA_DIR / "reinforce_log.csv"


class OnlineNormalizer:
    """
    Online normalizer:
      - counts -> log1p -> EMA mean/var -> z -> sigmoid -> (0,1)
      - money centered at money_threshold -> 0.5

    Default behavior returns 0.5 for a feature on its first call.
    """

    def __init__(self, alpha=0.02, eps=1e-6, money_threshold=5.0, money_scale=None):
        self.alpha = float(alpha)
        self.eps = float(eps)
        self.money_threshold = float(max(0.0, money_threshold))
        self.money_scale = None if money_scale is None else float(money_scale)
        self.stats = {}  # name -> {'mean': float, 'var': float}

    def _init_stat(self, name, x):
        self.stats[name] = {'mean': float(x), 'var': 0.0}

    def _update_ema(self, name, x):
        st = self.stats.get(name)
        if st is None:
            self._init_stat(name, x)
            return
        m = st['mean']
        v = st['var']
        a = self.alpha

        m_new = (1 - a) * m + a * x
        d = x - m_new
        v_new = (1 - a) * v + a * (d * d)
        st['mean'], st['var'] = m_new, v_new

    def _sigmoid(self, z):
        if z >= 0:
            ez = math.exp(-z)
            return 1.0 / (1.0 + ez)
        else:
            ez = math.exp(z)
            return ez / (1.0 + ez)

    def normalize_count(self, name, x):
        # Non-negative count -> normalized (0,1).
        x_log = math.log1p(max(0.0, x))
        if name not in self.stats:
            # initialize to current log value but return neutral 0.5 for first sample
            self._init_stat(name, x_log)
            return 0.5
        self._update_ema(name, x_log)
        st = self.stats[name]
        z = (x_log - st['mean']) / (math.sqrt(st['var']) + self.eps)
        return float(self._sigmoid(z))

    def normalize_money(self, name, money):
        """
        Money normalization centered on money_threshold -> 0.5.
        Uses log1p transform and running sigma unless money_scale specified.
        """
        m_val = math.log1p(max(0.0, money))
        thr_val = math.log1p(self.money_threshold)
        if name not in self.stats:
            # initialize mean at threshold to avoid early bias away from threshold
            self._init_stat(name, thr_val)
            # update once with actual money so variance starts
            self._update_ema(name, m_val)
            return 0.5
        self._update_ema(name, m_val)
        st = self.stats[name]
        sigma = math.sqrt(st['var']) + self.eps
        scale = self.money_scale if self.money_scale is not None else sigma
        z = (m_val - thr_val) / (scale + self.eps)
        return float(self._sigmoid(z))


class BloggerReinforcment:
    """
    Self-contained linear softmax policy for the blogger task.

    Raw state: [money, views, likes, comments, subs] (raw counts)
    Policy input: normalized state via OnlineNormalizer

    Default hyperparameters chosen to:
      - use raw counts in reward (money change, absolute subs, engagement rate)
      - encourage early normal posts via initial weight bias
    Actions: 0=post, 1=sponsored_post, 2=like_comments, 3=make_comments, 4=sleep
    """

    def __init__(
            self,
            normalizer=None,
            lr=5e-3,
            alpha_subs=0.1,
            beta_engagement=1.0,
            delta_views=1.0,
            money_penalty_coeff=2.0,
            money_threshold=100.0
    ):
        self.norm = normalizer or OnlineNormalizer(alpha=0.02, money_threshold=money_threshold)
        self.lr = float(lr)
        self.alpha_subs = float(alpha_subs)
        self.beta_engagement = float(beta_engagement)
        self.delta_views = float(delta_views)
        self.money_penalty_coeff = float(money_penalty_coeff)
        self.money_threshold = float(money_threshold)

        self.state_dim = 5
        self.action_dim = 5
        self.W = np.zeros((self.action_dim, self.state_dim))

        # Manual initialization to encourage early normal posts (action 0).
        # These weights operate on normalized features in [0,1] where 0.5 is neutral.
        # Values chosen so neutral state favors action 0.
        self.W[0, :] = np.array([-0.2, 1.2, 1.0, 0.4, 0.2])  # strong bias to "post"
        # sponsored posts prefer when money is low => negative on normalized money
        self.W[1, :] = np.array([-1.0, 0.0, 0.0, 0.0, 0.0])
        # like_comments and make_comments start neutral but can learn
        self.W[2, :] = np.zeros(self.state_dim)
        self.W[3, :] = np.zeros(self.state_dim)
        # discourage sleep slightly
        self.W[4, :] = np.array([-0.5, -0.2, -0.2, -0.2, -0.2])

    def _to_normalized(self, raw_state):
        # raw_state: iterable of length 5 -> normalized np.array of length 5
        m, v, l, c, s = raw_state
        return np.array([
            self.norm.normalize_money('money', m),
            self.norm.normalize_count('views', v),
            self.norm.normalize_count('likes', l),
            self.norm.normalize_count('comments', c),
            self.norm.normalize_count('subs', s)
        ], dtype=float)

    def _policy_probs(self, norm_state):
        logits = self.W.dot(norm_state)
        ex = np.exp(logits - np.max(logits))
        return ex / np.sum(ex)

    def get_action(self, raw_state):
        # Return (action:int, probs:np.array) given raw state.
        norm_s = self._to_normalized(raw_state)
        probs = self._policy_probs(norm_s)
        action = int(np.random.choice(self.action_dim, p=probs))
        return action, probs

    def compute_reward(self, prev_raw, next_raw):
        """
        Reward uses raw values:
          r = alpha_subs * subs_change + delta_views * views_change + beta_engagement * eng_rate_next - money_penalty
        engagement rate = (likes_next + comments_next) / max(views_next,1)
        """
        prev = np.asarray(prev_raw, dtype=float)
        nxt = np.asarray(next_raw, dtype=float)
        if prev.shape[0] != 5 or nxt.shape[0] != 5:
            raise ValueError("raw states must be length 5")

        subs_change = (nxt[4] - prev[4]) / max(1.0, prev[4])
        views_change = (nxt[1] - prev[1]) / max(1.0, prev[1])
        eng_rate = (nxt[2] + nxt[3]) / max(1.0, nxt[1])

        penalty = self.money_penalty_coeff * max(0.0, self.money_threshold - nxt[0])
        reward = self.alpha_subs * subs_change + self.delta_views * views_change + self.beta_engagement * eng_rate - penalty
        return float(reward)

    def update(self, prev_raw, action, next_raw, baseline=0.0):
        """
        REINFORCE update using reward computed from raw states.
        Returns computed reward.
        """
        reward = self.compute_reward(prev_raw, next_raw)
        norm_prev = self._to_normalized(prev_raw)
        probs = self._policy_probs(norm_prev)
        grad_logp = -np.outer(probs, norm_prev)  # shape (A, S)
        grad_logp[action] += norm_prev
        self.W += self.lr * (reward - baseline) * grad_logp
        return reward

    def save(self, path: str | os.PathLike = STATE_PATH):
        """Сохранить веса W, скорость обучения и статистику нормализации."""
        np.savez(
            path,
            W=self.W,
            lr=self.lr,
            norm_keys=np.array(list(self.norm.stats.keys()), dtype=object),
            norm_mean=np.array([self.norm.stats[k]['mean'] for k in self.norm.stats]),
            norm_var=np.array([self.norm.stats[k]['var'] for k in self.norm.stats]),
        )

    def load(self, path: str | os.PathLike = STATE_PATH) -> bool:
        """Загрузить состояние (если файл есть). Возвращает True/False."""
        p = Path(path)
        if not p.exists():
            return False
        z = np.load(p, allow_pickle=True)
        self.W = z["W"]
        self.lr = float(z["lr"])
        keys = list(z["norm_keys"])
        means = list(z["norm_mean"])
        vars_ = list(z["norm_var"])
        self.norm.stats = {k: {"mean": float(m), "var": float(v)} for k, m, v in zip(keys, means, vars_)}
        return True

    # === DEBUG / OBSERVABILITY ===
    def debug_params(self) -> dict:
        """Вернуть текущие веса и статистику нормализации (для дебага/эндпоинта)."""
        stats = {k: dict(v) for k, v in self.norm.stats.items()}
        return {"W": self.W.copy(), "norm_stats": stats, "lr": self.lr}

    def action_probs(self, raw_state: list[float]) -> np.ndarray:
        """Распределение вероятностей действий для произвольного состояния."""
        s = self._to_normalized(raw_state)
        return self._policy_probs(s)

    # === (опционально) CSV-лог шага обучения ===
    def log_step(self, reward: float, action: int, prev_state: list[float], next_state: list[float], probs):
        newfile = not LOG_PATH.exists()
        with open(LOG_PATH, "a", newline="") as f:
            w = csv.writer(f)
            if newfile:
                w.writerow([
                    "ts", "reward", "action",
                    "prev_money", "prev_views", "prev_likes", "prev_comments", "prev_subs",
                    "next_money", "next_views", "next_likes", "next_comments", "next_subs",
                    "p_post", "p_sponsored", "p_like_comments", "p_make_comments", "p_sleep"
                ])
            row = [
                int(time.time()), float(reward), int(action),
                *map(float, prev_state),
                *map(float, next_state),
                *map(lambda x: round(float(x), 6), probs),
            ]
            w.writerow(row)

