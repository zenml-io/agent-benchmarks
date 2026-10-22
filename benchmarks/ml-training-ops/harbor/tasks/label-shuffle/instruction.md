A colleague added shuffling to the data pipeline in /app (`python /app/train.py`). Since then the
model's accuracy is stuck around chance level even though the loss goes down a little. Find and
fix the bug in the data pipeline so the model learns properly again. Do not change the model,
optimizer or hyperparameters. The job must still save its weights to /app/model.pt.
