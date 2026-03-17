source .venv/bin/activate
uv pip install -e ".[dev]"

uv build
uv sync --extra validation


export OPENAI_API_KEY=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
export ANTHROPIC_API_KEY=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

agentspan doctor
python3 -m validation.scripts.run_examples --group=SMOKE_TEST -j
#python3 -m validation.scripts.run_examples --group=OPENAI_EXAMPLES -j
agentspan doctor

python3 -m validation.scripts.judge_results

#agentspan doctor
#python examples/01_basic_agent.py
#agentspan doctor
#agentspan server stop
#agentspan doctor

#agentspan doctor
#python3 -m validation.scripts.run_examples --group=SMOKE_TEST
#agentspan doctor
#agentspan server stop
