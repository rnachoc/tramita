# ADR 0003: Build the agent loop on the plain Anthropic SDK

- Status: accepted
- Date: 2026-10-20

## Context

Tramita runs a coordinator and three specialist agents (coverage, damage, fraud). Each agent needs
its own tools, a step budget, timeouts, structured outputs validated against a schema, prompt
caching for policy terms, tracing of every model and tool call with the OpenTelemetry GenAI
conventions, and a deterministic fake model for tests and CI.

## Options considered

1. **A general agent framework** (LangChain/LangGraph, LlamaIndex agents, CrewAI and similar).
   Fast to prototype. They add layers between the code and the model API: prompts and tool schemas
   are generated for us, retries and memory are implicit, and upgrades frequently change behaviour.
   Faking the model deterministically, or tracing exactly what was sent, means working against
   the abstraction.
2. **A provider-agnostic thin wrapper** (for example a multi-provider client). Smaller, but the
   lowest common denominator hides provider features this project relies on: prompt caching,
   batch API, structured outputs and vision.
3. **An own loop on the official Anthropic SDK.** Roughly a few hundred lines: send messages, run
   the requested tools, append results, stop on a final answer, a step limit or a timeout.

## Decision

Option 3. The loop is small enough to read in one sitting and is the code most worth owning,
because it is where safety properties live:

- Tools are typed Python functions with Pydantic input models. Invalid tool input returns an error
  message the model can read and correct, instead of an exception that kills the run.
- Every agent has an explicit step budget and wall-clock timeout.
- Tool output and document text are always passed as data inside tool results, never concatenated
  into the system prompt (prompt-injection resistance).
- The model client is an interface with two implementations: the Anthropic SDK and a deterministic
  fake that replays recorded responses. Tests, CI and keyless runs use the fake.

## Consequences

- Full control over prompts, caching breakpoints, retries and tracing; nothing implicit.
- We maintain the loop ourselves, including tool-error handling and limits. This is covered by
  unit tests against the fake model.
- Switching model provider would mean writing another client implementation, which is acceptable
  because the project deliberately uses Claude-specific features.
