import random
import time
# STEP 1 CHANGE 1: import uuid for generating unique IDs
import uuid
# STEP 3 CHANGE 1: import json for structured event output
import json


# STEP 3 CHANGE 2: single emit() helper — all events go through here as JSON
def emit(event_data):
    print(json.dumps(event_data))


class Agent:
    """A simulated agent that does N steps of work. Pure simulation — no LLM, no network."""
    def __init__(self, name, steps, fail_at_step=None):
        self.name = name
        self.steps = steps
        self.fail_at_step = fail_at_step

    # STEP 1 CHANGE 2: added span_id parameter so each agent receives its unique ID
    def run(self, listener, span_id):
        for step in range(1, self.steps + 1):
            time.sleep(random.uniform(0.05, 0.2))
            if self.fail_at_step and step == self.fail_at_step:
                raise RuntimeError(f"{self.name} failed at step {step}")
            # STEP 1 CHANGE 3: pass span_id into listener on every call
            listener(self.name, step, self.steps, span_id)


class Orchestrator:
    # STEP 3 CHANGE 3: added trace_id parameter so Orchestrator can stamp its own events
    def __init__(self, agents, listener, trace_id):
        self.agents = agents
        self.listener = listener
        self.trace_id = trace_id

    def run(self):
        # STEP 4 CHANGE 1: track completed agents for run_summary
        completed = []

        for agent in self.agents:
            # STEP 1 CHANGE 4: generate a fresh span_id per agent
            span_id = str(uuid.uuid4())
            # STEP 2 CHANGE 1: record agent start time for duration calculation
            agent_start = time.time()

            # STEP 3 CHANGE 4: emit agent_started event before agent runs
            emit({
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "trace_id": self.trace_id,
                "span_id": span_id,
                "event": "agent_started",
                "agent": agent.name
            })

            # STEP 4 CHANGE 2: wrap in try/except to catch agent failures cleanly
            try:
                agent.run(self.listener, span_id)
                # STEP 2 CHANGE 2: compute duration after agent finishes
                duration = round(time.time() - agent_start, 3)

                # STEP 3 CHANGE 5: emit agent_completed with duration
                emit({
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "trace_id": self.trace_id,
                    "span_id": span_id,
                    "event": "agent_completed",
                    "agent": agent.name,
                    "duration": duration
                })

                # STEP 4 CHANGE 3: record this agent as successfully completed
                completed.append(agent.name)

            except RuntimeError as e:
                # STEP 2 CHANGE 3: compute duration even on failure
                duration = round(time.time() - agent_start, 3)

                # STEP 4 CHANGE 4: emit agent_failed — captures which agent, which step, error
                emit({
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "trace_id": self.trace_id,
                    "span_id": span_id,
                    "event": "agent_failed",
                    "agent": agent.name,
                    "error": str(e),
                    "duration": duration
                })

                # STEP 4 CHANGE 5: emit run_summary on failure and stop pipeline
                emit({
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "trace_id": self.trace_id,
                    "event": "run_summary",
                    "status": "failed",
                    "failed_agent": agent.name,
                    "agents_completed": completed
                })
                return  # STEP 4 CHANGE 6: stop pipeline cleanly after failure

        # STEP 4 CHANGE 7: emit run_summary on success after all agents finish
        emit({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "trace_id": self.trace_id,
            "event": "run_summary",
            "status": "success",
            "failed_agent": None,
            "agents_completed": completed
        })


# STEP 1 CHANGE 5: replaced plain progress_listener with make_listener() closure
# STEP 2 CHANGE 4: added total_steps and run_start_time parameters for pipeline metrics
def make_listener(trace_id, total_steps, run_start_time):

    # STEP 2 CHANGE 5: steps_done counter persists across all agents via closure
    steps_done = 0

    def progress_listener(agent_name, step, total_steps_agent, span_id):
        nonlocal steps_done
        # STEP 2 CHANGE 6: increment counter on every step
        steps_done += 1

        # STEP 2 CHANGE 7: compute pipeline % complete across all agents
        pct = steps_done / total_steps * 100

        # STEP 2 CHANGE 8: compute throughput — steps per second since run started
        throughput = round(steps_done / (time.time() - run_start_time), 2)

        # STEP 3 CHANGE 6: throttle — only emit at first, last, or every ~25% of steps
        # avoids noisy over-emission on long agents
        should_emit = (
            step == 1
            or step == total_steps_agent
            or step % max(1, total_steps_agent // 4) == 0
        )

        if should_emit:
            # STEP 3 CHANGE 7: replace print() with structured JSON emit
            emit({
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "trace_id": trace_id,
                "span_id": span_id,
                "event": "agent_progress",
                "agent": agent_name,
                "step": step,
                "total_steps": total_steps_agent,
                "pipeline_pct": round(pct, 1),
                "throughput": throughput
            })

    return progress_listener


def main():
    agents = [
        Agent("Planner", 3),
        Agent("Researcher", 6),
        Agent("Writer", 4),
        Agent("Reviewer", 2),
        # STEP 4: uncomment below to test failure path
        # Agent("Writer", 4, fail_at_step=2),
    ]

    # STEP 1 CHANGE 6: generate one trace_id for the entire pipeline run
    trace_id = str(uuid.uuid4())

    # STEP 2 CHANGE 9: compute total steps across all agents
    total_steps = sum(a.steps for a in agents)

    # STEP 2 CHANGE 10: record run start time for throughput calculation
    run_start_time = time.time()

    # STEP 1 CHANGE 7: pass make_listener instead of plain progress_listener
    # STEP 2 CHANGE 11: pass total_steps and run_start_time into make_listener
    # STEP 3 CHANGE 8: pass trace_id into Orchestrator so it can stamp its events
    Orchestrator(
        agents,
        make_listener(trace_id, total_steps, run_start_time),
        trace_id
    ).run()


if __name__ == "__main__":
    main()