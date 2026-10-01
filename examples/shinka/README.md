# Synthetic Shinka task

This example uses only Python's standard library and tiny CPU calculations.
It contains no private research data. Generated search results are not scientific
evidence. Running **Shinka evolution** additionally requires the optional backend,
an explicit supported model identifier, and the corresponding provider access.

From the LabWeft checkout, without installing Shinka or contacting any model:

```sh
python labweft.py init ./shinka-demo --name "Synthetic Shinka example"
python labweft.py research prepare ./shinka-demo examples/shinka/campaign.json
python labweft.py research start ./shinka-demo synthetic-square
python labweft.py research status ./shinka-demo synthetic-square
```

The start command above is a **dry run**, not an experiment. To actually evolve
the program, first replace the placeholder model in a copy of `campaign.json`
and prepare a **new activity id**; the contract of an existing id is immutable.
Use an absolute `task_dir` if you move the JSON elsewhere. Then follow the
[backend guide](../../docs/AUTORESEARCH.md).

You can independently run the frozen evaluator on the supplied baseline without
a model, Shinka or GPU:

```sh
python examples/shinka/task/evaluate.py --program_path examples/shinka/task/initial.py --results_dir ./shinka-demo/baseline-check
```

The baseline is valid code with a nonzero error. An invalid program is recorded
as `correct=false`; it is not omitted from the experiment history. In this
synthetic task `correct` means the function produced finite values, not that its
predictions exactly matched the target.
