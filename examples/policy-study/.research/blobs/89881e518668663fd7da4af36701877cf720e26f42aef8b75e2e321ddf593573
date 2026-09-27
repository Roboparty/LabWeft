"""Synthetic, illustrative model interface; no real training is performed."""

class HistoryEncoder:
    def __init__(self, history_length=3):
        self.history_length = history_length

    def encode(self, observations):
        return observations[-self.history_length:] if self.history_length else observations[-1:]


def auxiliary_objective(prediction, target, weight):
    # Purely illustrative. Do not interpret demo numbers as outputs of this function.
    return weight * sum((p - t) ** 2 for p, t in zip(prediction, target))
