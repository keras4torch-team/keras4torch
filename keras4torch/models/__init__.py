import torch
from torch.utils.data import DataLoader, TensorDataset
import torchsummary
from collections import OrderedDict
from torch.utils.data import random_split

from .._training import Trainer
from ..layers import KerasLayer
from ..metrics import Metric
from ..metrics import create_metric_by_name
from ..losses import create_loss_by_name
from ..optimizers import create_optimizer_by_name
from ..utils import to_tensor

class Model(torch.nn.Module):
    """
    `Model` wraps a `nn.Module` with training and inference features.

    Once the model is wrapped, you can config the model with losses and metrics\n  with `model.compile()`, train the model with `model.fit()`, or use the model\n  to do prediction with `model.predict()`.
    """
    def __init__(self, model):
        super(Model, self).__init__()
        self.model = model
        self.compiled = False
        self.built = False

        self.has_keras_layer = False
        def check_keras_layer(m):
            if isinstance(m, KerasLayer):
                self.has_keras_layer = True
        self.model.apply(check_keras_layer)

    def forward(self, x):
        return self.model.forward(x)

    def count_params(self) -> int:
        """Count the total number of scalars composing the weights."""
        return sum([p.numel() for p in self.parameters()])

    ########## keras-style methods below ##########

    @torch.no_grad()
    def build(self, input_shape):
        """Build the model when it contains `KerasLayer`."""
        if self.has_keras_layer:
            input_shape = [2] + list(input_shape)
            probe_input = torch.zeros(size=input_shape)
            self.model.forward(probe_input)
        self.built = True
        return self

    def _check_keras_layer(self):
        if self.has_keras_layer and not self.built:
            raise AssertionError("You should call `model.build()` first because the model contains `KerasLayer`.")

    def summary(self, input_shape, depth=3):
        """Print a string summary of the network."""
        self._check_keras_layer()
        torchsummary.summary(self.model, input_shape, depth=depth, verbose=1)

    def compile(self, optimizer, loss, metrics=None, device=None):
        """
        Configure the model for training.

        Args:

        * `optimizer`: String (name of optimizer) or optimizer instance.

        * `loss`: String (name of objective function), objective function or loss instance.

        * `metrics`: List of metrics to be evaluated by the model during training. You can also use dict to specify the 
        abbreviation of each metric.

        * `device`: Device of the model and its trainer, if `None` 'cuda' will be used when `torch.cuda.is_available()` otherwise 'cpu'.
        """
        self._check_keras_layer()
        if device == None:
            device = 'cuda' if torch.cuda.is_available() else 'cpu'
            
        if isinstance(loss, str):
            loss = create_loss_by_name(loss)
        if isinstance(optimizer, str):
            optimizer = create_optimizer_by_name(optimizer, self.parameters())

        m = OrderedDict({'loss': loss})
        if isinstance(metrics, dict):
            m.update(metrics)
        elif isinstance(metrics, list):
            for tmp_m in metrics:
                if isinstance(tmp_m, str):
                    tmp_m = create_metric_by_name(tmp_m)
                if isinstance(tmp_m, Metric):
                    m[tmp_m.get_abbr()] = tmp_m
                    tmp_m.set_device(device)
                elif hasattr(tmp_m, '__call__'):
                    m[tmp_m.__name__] = tmp_m
                else:
                    raise TypeError('Unsupported type.')
        elif not (metrics is None):
            raise TypeError('Argument `metrics` should be either a dict or list.')

        self.to(device=device)
        self.trainer = Trainer(model=self, optimizer=optimizer, loss=loss, metrics=m, device=device)
        self.compiled = True


    def fit_dl(self, train_loader, epochs,
                val_loader=None,
                callbacks=[],
                verbose=1,
                precise_train_metrics=False):

        self.trainer.register_callbacks(callbacks)
        history = self.trainer.run(train_loader, val_loader, max_epochs=epochs, verbose=verbose, precise_train_metrics=precise_train_metrics)

        return history


    def fit(self, x, y, epochs, batch_size=32,
                validation_split=None, val_split_seed=7,
                validation_data=None,
                callbacks=[],
                verbose=1,
                precise_train_metrics=False,
                shuffle=True,
                sample_weight=None
                ):
        """Train the model for a fixed number of epochs (iterations on a dataset)."""

        assert self.compiled
        x, y = to_tensor(x, y)

        assert not (validation_data != None and validation_split != None)
        has_val = validation_data != None or validation_split != None

        if type(sample_weight) != type(None):
            if isinstance(sample_weight, list):
                sample_weight = torch.tensor(sample_weight)
            sample_weight = to_tensor(sample_weight).float()
            train_set = TensorDataset(x, y, sample_weight)
        else:
            train_set = TensorDataset(x, y)

        if validation_data != None:
            x_val, y_val = to_tensor(validation_data[0], validation_data[1])
            val_set = TensorDataset(x_val, y_val)

        if validation_split != None:
            val_length = int(len(train_set) * validation_split)
            train_length = len(train_set) - val_length
            train_set, val_set = random_split(train_set, [train_length, val_length], generator=torch.Generator().manual_seed(val_split_seed))

        train_loader = DataLoader(train_set, batch_size=batch_size, shuffle=shuffle)
        val_loader = DataLoader(val_set, batch_size=batch_size, shuffle=False) if has_val else None

        # Training
        self.trainer.register_callbacks(callbacks)
        history = self.trainer.run(train_loader, val_loader, max_epochs=epochs, verbose=verbose, precise_train_metrics=precise_train_metrics)

        return history

    @torch.no_grad()
    def evaluate(self, x, y=None, batch_size=32):
        """Return the loss value & metrics values for the model in test mode.\n\n    Computation is done in batches."""
        assert self.compiled
        if not (y is None):
            x, y = to_tensor(x, y)
            val_loader = DataLoader(TensorDataset(x, y), batch_size=batch_size, shuffle=False)
            return self.trainer.evaluate(val_loader)
        else:
            return self.trainer.evaluate(x)

    @torch.no_grad()
    def predict(self, inputs, batch_size=32, device=None, output_numpy=True, activation=None):
        """
        Generate output predictions for the input samples.\n\n    Computation is done in batches.
        """
        self._check_keras_layer()

        if device == None:
            if self.compiled:
                device = self.trainer.device
            else:
                device = 'cuda' if torch.cuda.is_available() else 'cpu'

        self.eval().to(device=device)

        if isinstance(inputs, DataLoader):
            data_loader = inputs
        else:
            inputs = to_tensor(inputs)
            data_loader = DataLoader(TensorDataset(inputs), batch_size=batch_size, shuffle=False)

        outputs = []
        for x_batch in data_loader:
            outputs.append(self.forward(x_batch[0].to(device=device)))

        outputs = torch.cat(outputs, dim=0)

        if activation != None:
            outputs = activation(outputs)

        if output_numpy:
            return outputs.cpu().numpy()
        else:
            return outputs

    def save_weights(self, filepath):
        """Equal to `torch.save(model.state_dict(), filepath)`."""
        torch.save(self.state_dict(), filepath)

    def load_weights(self, filepath):
        """Equal to `model.load_state_dict(torch.load(filepath))`."""
        self.load_state_dict(torch.load(filepath))






from .xwbank2020 import conv1d_xwbank2020