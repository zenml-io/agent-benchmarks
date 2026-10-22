import json


class History:
    def __init__(self):
        self.losses = []
        self.grad_norms = []

    def log(self, loss, grad_norm):
        self.losses.append(loss)
        self.grad_norms.append(grad_norm)

    def smoothed(self, k=50):
        tail = self.losses[-k:]
        return sum(tail) / len(tail)

    def dump(self, path):
        json.dump({"loss_history": [float(l) for l in self.losses],
                   "grad_norm_history": [float(g) for g in self.grad_norms]}, open(path, "w"))
