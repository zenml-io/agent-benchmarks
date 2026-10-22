import torch
import torch.nn as nn
from data import make_data


class ShuffledDataset:
    """Shuffles the training set once per epoch."""

    def __init__(self, X, y, seed=0):
        self.X, self.y, self.g = X, y, torch.Generator().manual_seed(seed)

    def epoch(self):
        xi = torch.randperm(len(self.X), generator=self.g)
        yi = torch.randperm(len(self.y), generator=self.g)
        return self.X[xi], self.y[yi]


def build_model():
    return nn.Sequential(nn.Linear(32, 128), nn.ReLU(), nn.Linear(128, 4))


def main():
    torch.manual_seed(0)
    X, y = make_data(8192, seed=1)
    ds = ShuffledDataset(X, y)
    model = build_model()
    opt = torch.optim.Adam(model.parameters(), lr=3e-3)
    for epoch in range(8):
        Xe, ye = ds.epoch()
        for i in range(0, len(Xe), 256):
            loss = nn.functional.cross_entropy(model(Xe[i:i + 256]), ye[i:i + 256])
            opt.zero_grad()
            loss.backward()
            opt.step()
        print(f"epoch {epoch} loss {loss.item():.4f}")
    torch.save(model.state_dict(), "/app/model.pt")


if __name__ == "__main__":
    main()
