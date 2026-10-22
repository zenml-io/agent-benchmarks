/app/train.py trains a model with dropout and batch normalization and reports validation accuracy
after every epoch in /app/metrics.json. The reported validation accuracy is noisy, lower than
expected, and evaluating changes the model. Fix the evaluation so that it reports the model's
true validation accuracy and leaves the model unchanged, without changing the model or the
training loop.
