"""Analysis tools orchestrated by the AnomalEye agent.

Each tool is a small, self-contained capability with a clear input/output
contract so the agent can compose them in any order the query demands:

* :mod:`anomaleye.tools.eda`      — exploratory data analysis / profiling
* :mod:`anomaleye.tools.features` — AML feature engineering
* :mod:`anomaleye.tools.anomaly`  — hybrid anomaly / typology detection
* :mod:`anomaleye.tools.risk`     — score -> risk band + escalation
* :mod:`anomaleye.tools.explain`  — natural-language flag explanations
"""
