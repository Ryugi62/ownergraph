def hit_at_k(predicted, truth, k: int) -> int:
    return int(bool(set(predicted[:k]) & set(truth)))


def mrr(predicted, truth) -> float:
    for i, p in enumerate(predicted, 1):
        if p in truth:
            return 1.0 / i
    return 0.0
