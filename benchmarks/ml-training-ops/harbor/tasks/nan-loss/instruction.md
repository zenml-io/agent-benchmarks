The training job in /app (`python /app/train.py`) produces NaN losses after the first few steps
and the saved model is useless. Find and fix the cause so that training is numerically stable
and the model learns.

Constraints: keep the model architecture, its initialization, the optimizer, the learning rate,
the batch size and the number of steps exactly as they are. The job must still save the trained
weights to /app/model.pt.
