# Losses

## String Named Losses

```python
OrderedDict({
    'mse': nn.MSELoss,
    'mae': nn.L1Loss,
    'ce_loss': nn.CrossEntropyLoss,
    'bce_loss': nn.BCEWithLogitsLoss,
})
```



## Others

#### `losses.CELoss()`

It is an alternative to `nn.CrossEntropy`, which integrates label smoothing.

```python
loss_fn = keras4torch.losses.CELoss(label_smoothing=0.1)
```



