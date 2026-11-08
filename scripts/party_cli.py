"""party's command line, with two fixes for this env (party at commit c2589b1, Kraken 7.1.1, Python 3.11).

1. Kraken 7.1.1 finds the model that made a checkpoint by each registered model's `_config_class`
   (kraken/models/convert.py, find_checkpoint_module). party registers its model (party.model:PartyRecognitionModel)
   but gives it none, so Kraken skips it and no party checkpoint converts: `party train` stops after training,
   converting its best checkpoint into best_<loss>.safetensors, and scripts/party_finetune.py's conversions would stop
   the same way.
2. party/report.py opens party/scripts.json by `importlib.resources.files(__name__)`, `__name__` being the module
   party.report. Python takes a module there only from 3.12; 3.11 takes a package only, so `party test` stops once it
   has read the test lines. That lookup is given the package, which holds scripts.json.
Importing this module applies both.
Usage: python scripts/party_cli.py <party's arguments>, as `party`.
"""
import importlib.resources
from types import SimpleNamespace

import party.report
from party.configs import PartyRecognitionTrainingConfig
from party.model import PartyRecognitionModel

PartyRecognitionModel._config_class = PartyRecognitionTrainingConfig
party.report.resources = SimpleNamespace(files=lambda anchor: importlib.resources.files("party"))

if __name__ == "__main__":
    from party.cli import cli
    cli()
