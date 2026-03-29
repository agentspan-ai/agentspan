#!/usr/bin/env python3
"""Run — trigger the deployed ML pipeline by name.

Requires: deploy.py has been run AND serve.py is running.

CLI equivalent:
    agentspan run ml_pipeline "Build a model for California housing prices."
"""

from agentspan.agents import AgentRuntime

PROMPT = (
    "Build a model to predict California housing prices. The dataset has 20,640 "
    "samples with 8 features: MedInc, HouseAge, AveRooms, AveBedrms, Population, "
    "AveOccup, Latitude, Longitude. Target: MedianHouseValue (continuous, in $100k "
    "units). Metric: RMSE. Some features have skewed distributions."
)

with AgentRuntime() as rt:
    result = rt.run("ml_pipeline", PROMPT)
    print(f"Status: {result.status}")
    result.print_result()
