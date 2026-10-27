# Your agent goes here

This folder is empty on purpose.

Everything else in this repository exists so that you don't spend your morning on setup:
the data is sourced, the licensing is checked, the load process is written, and the
exploration queries are ready to run. That is the on-ramp.

The agent is the part that's actually yours. We haven't written a scaffold, a starter
class, or a "fill in the blanks" template, because the design decisions you make here are
what you'll be judged on and what you'll demo.

## One requirement worth repeating

Your agent must **call** your BigQuery ML prediction, not just query historical rows. A
tool you built—a Python function tool, or your own MCP Toolbox definition—that runs `ML.PREDICT`
(or better, `ML.EXPLAIN_PREDICT`) against the model your data lane trains is the shape most teams
will land on.

The per-feature attributions that come back from `ML.EXPLAIN_PREDICT` are what turn a
location into a recommendation a city planner can defend. Don't treat the explanation as
a reporting step at the end—it's the product.

Build it however your team works best. Delete this file when you do.
