# Autonomous AI Trading System

An autonomous paper-trading system for **US Stocks and Options** built around bounded adaptive decision-making, deterministic risk controls, safe execution, live market monitoring, and outcome-based learning.

The system is designed for autonomous operation while still allowing human interaction through the same account and execution infrastructure.

The core objective is not to create a traditional fixed-rule trading bot and not to put an LLM in a continuous trading loop.

Instead, the system is designed to:

- observe the market continuously;
- discover relevant opportunities autonomously;
- evaluate market context and regime;
- compare multiple bounded trading hypotheses;
- gather only the evidence required for the decision;
- decide whether to trade or abstain;
- send only bounded proposals through the existing admission and risk system;
- execute through the controlled execution layer;
- monitor outcomes;
- learn conservatively from mature results;
- remain auditable and safe throughout the process.

---

# Project Status

## Current Status

### Autonomous Stocks

**Implemented and operational.**

The system can independently:

1. discover stock opportunities;
2. add relevant symbols to the monitoring universe;
3. receive market data;
4. detect meaningful market events;
5. open an autonomous decision cycle;
6. build market and portfolio context;
7. estimate market regime;
8. evaluate bounded hypotheses;
9. compare candidate approaches;
10. select a trade or `NO_TRADE`;
11. create a bounded proposal;
12. send it through Admission;
13. run the proposal through the authoritative Risk Engine;
14. execute through CORE-X;
15. monitor the eventual outcome;
16. update future hypothesis preference after the outcome matures.

This is the currently completed autonomous trading capability.

### Autonomous Options

**Options infrastructure exists, but autonomous options decision-making is not yet connected to the decision layer.**

The project already contains options-related risk and validation infrastructure, including option-specific data filtering and structural validation.

However, the current autonomous hypothesis registry is still stock-focused.

Therefore the current system should be accurately described as:

> **Autonomous Stock Trading with Existing Options Infrastructure**

and not yet as:

> **Fully Autonomous Stock + Options Trading**

The next major milestone is to connect options to the same autonomous decision process so the system can independently choose between:

- Stock
- Option
- `NO_TRADE`

for a qualifying underlying opportunity.

---

# Project Goal

The long-term goal is a unified autonomous trading system capable of making asset-class decisions itself.

For a qualifying market opportunity, the system should eventually be able to determine:

- whether there is a meaningful opportunity;
- whether a stock position is preferable;
- whether an option position is preferable;
- whether neither is attractive;
- how much evidence is available;
- how confident the decision should be;
- whether the proposal is allowed by the risk system;
- whether execution succeeded, was rejected, or became uncertain;
- how the eventual outcome should influence future decisions.

The system is intentionally designed so that autonomous intelligence can adapt its preferences without being allowed to modify the safety system.

---

# What Makes the System Autonomous

The project does not define autonomy as:

> "Run a strategy automatically."

It defines autonomy as the ability to independently move through:

**Observe → Understand Context → Compare Hypotheses → Gather Evidence → Decide → Propose → Risk Check → Execute → Observe Outcome → Learn**

The system should therefore be able to make decisions such as:

- continue with a directional opportunity;
- prefer another available approach;
- reduce or avoid exposure;
- reject an opportunity because evidence quality is insufficient;
- choose `NO_TRADE`;
- change future hypothesis preference after enough mature outcomes;
- reduce confidence when market conditions drift.

The system must not require a human to manually select a strategy for every autonomous market event.

---

# Main Functional Capabilities

## Autonomous Market Discovery

The system can discover equities without requiring the user to manually specify every symbol.

The discovery process uses supported market information to identify potentially relevant securities and feed them into the dynamic market universe.

Discovered symbols are then made available to the monitoring/streaming system.

The universe is aware of different symbol sources, including:

- portfolio holdings;
- user-intent symbols;
- market-context symbols;
- autonomously discovered symbols.

The system protects important portfolio symbols while allowing lower-priority discovery symbols to be managed dynamically.

---

# Dynamic Market Universe

The project maintains a bounded market universe instead of attempting to monitor an unlimited number of symbols.

The universe supports:

- portfolio-aware monitoring;
- user-intent monitoring;
- default market context;
- autonomous discovery;
- duplicate prevention;
- bounded capacity;
- dynamic subscription changes.

The purpose is to continuously monitor the symbols that matter most without creating unnecessary data or CPU load.

Portfolio holdings receive stronger protection than temporary discovery candidates.

---

# Market Data Monitoring

The autonomous system continuously consumes available market information through the configured Alpaca data integration.

The streaming layer is responsible for:

- receiving market data;
- normalizing events;
- filtering irrelevant noise;
- detecting potentially material movement;
- passing meaningful events into the autonomous decision process.

The UI is not intended to display every market tick.

Raw market activity is processed internally, while the user-facing console displays meaningful state changes and autonomous decisions.

---

# Market Event Detection

The autonomous system does not need to open a full decision cycle for every quote.

A market event first passes through deterministic filtering and deduplication.

This prevents:

- unnecessary decision cycles;
- repeated identical analysis;
- LLM spam;
- excessive network requests;
- excessive UI noise.

The event system uses deterministic fingerprinting and cooldown behavior to prevent repeated processing of the same opportunity.

---

# Autonomous Decision Cycle

When a meaningful event is detected, the system opens an autonomous decision cycle.

A decision cycle evaluates the current opportunity rather than immediately converting a market event into an order.

The cycle includes:

1. market event context;
2. current price and movement;
3. account context;
4. portfolio exposure;
5. broader market state;
6. regime estimate;
7. eligible hypotheses;
8. required evidence;
9. confidence;
10. uncertainty;
11. final selection;
12. proposal creation if appropriate.

A trigger is therefore a reason to investigate an opportunity, not an automatic order instruction.

---

# Context and Market State

The decision layer builds a structured context snapshot before choosing an action.

Relevant context can include:

- symbol price;
- recent movement;
- account equity;
- portfolio exposure;
- market context;
- SPY state;
- volatility information;
- data freshness;
- regime state;
- available evidence.

The context snapshot is intended to explain and support a decision.

It does not replace the authoritative facts retrieved by the Risk Engine immediately before execution.

---

# Market Regime

The autonomous decision system maintains a small market-state representation rather than treating every market event identically.

The current implementation uses regime estimation based on broader market conditions such as:

- SPY behavior;
- moving-average context;
- volatility/ATR-related information;
- persistence/hysteresis.

The purpose is to prevent a single noisy market update from immediately changing the system's interpretation of the market.

Regime changes therefore require persistence rather than reacting to a single observation.

---

# Hypothesis-Based Decision Making

The autonomous system uses a bounded hypothesis registry rather than an unrestricted strategy generator.

Current autonomous stock hypotheses include concepts such as:

- trend continuation;
- mean reversion;
- defensive reduction;
- `NO_TRADE`.

The exact eligibility of each hypothesis depends on the current context and regime.

A hypothesis may be:

- eligible;
- ineligible;
- lower-confidence;
- shadow/degraded;
- preferred;
- rejected because required evidence is missing.

The system does not need to execute a trade simply because an event occurred.

---

# NO_TRADE

`NO_TRADE` is a first-class decision.

It is not treated as:

- an error;
- a missing strategy;
- a failed execution;
- a system failure.

The autonomous system may intentionally choose `NO_TRADE` when:

- confidence is insufficient;
- evidence is stale;
- evidence is missing;
- market conditions are unfavorable;
- the available approaches are weak;
- portfolio constraints make the opportunity unsuitable;
- the system cannot distinguish a sufficiently attractive action from uncertainty.

A valid autonomous system must be capable of doing nothing when doing nothing is the better decision.

---

# Contextual Selection

The system uses a bounded contextual selector to rank eligible hypotheses.

The selector combines the current decision context with historical information about previously observed outcomes.

The current implementation uses a Bayesian-style Beta posterior representation for hypothesis preference.

Conceptually, the system combines:

- the current hypothesis's base confidence;
- historical outcome information;
- the current market context;
- current regime.

This means the system is not limited to one permanently preferred strategy.

As mature outcomes accumulate, future decisions can be influenced by what has historically worked better under comparable conditions.

---

# Adaptive Learning

The autonomous system is designed to adapt without modifying its source code.

Learning occurs at the decision-preference level rather than the code or safety-policy level.

The system can adapt:

- hypothesis preference;
- confidence weighting;
- contextual ranking;
- regime-specific preference;
- evidence preference.

The system cannot autonomously change:

- risk limits;
- capital limits;
- position limits;
- execution permissions;
- safety policies;
- CORE-X behavior;
- authoritative Risk Engine rules.

This separation is critical.

The goal is:

> adaptive decision intelligence inside immutable safety boundaries.

---

# Outcome Evaluation

Autonomous decisions are not considered learned immediately after execution.

The system schedules an outcome evaluation after a predefined horizon.

The current production default outcome horizon is:

**300 seconds**

The horizon can be overridden through configuration/environment when required, but the default remains 300 seconds.

The outcome monitor retrieves the relevant market information and evaluates the eventual result.

The result is then written to the durable decision/outcome storage.

---

# Learning From Mature Outcomes

Only mature outcomes are intended to influence future hypothesis preference.

The system does not update strategy preference simply because:

- a position is temporarily profitable;
- an unrealized price changed;
- a trade is still open;
- a single noisy quote appeared.

Instead, the outcome is evaluated at the predefined decision horizon.

The resulting record can then influence the Bayesian preference information used by later autonomous decisions.

This creates a feedback loop:

**Decision → Outcome → Learning → Future Decision Preference**

---

# Regime-Aware Adaptation

Learning is intended to remain contextual rather than treating all market environments as identical.

The system can account for different conditions such as:

- normal/trending conditions;
- range-like conditions;
- stressed/high-volatility conditions.

The purpose is to avoid learning the wrong lesson from one market regime and applying it blindly to another.

---

# Drift Detection

The autonomous layer also monitors for evidence that previously useful behavior may no longer be performing as expected.

Drift can cause the system to:

- reduce confidence;
- stop promoting an approach;
- move an approach into shadow/degraded behavior;
- delay aggressive preference changes.

Drift must never cause the system to loosen safety controls.

---

# Shadow / Conservative Behavior

When confidence is weak or behavior appears to be drifting, the system should be capable of evaluating an approach without giving it unrestricted execution authority.

This is intended to reduce the risk of the autonomous system overreacting to a short sequence of unusual outcomes.

The system should prefer:

- abstention;
- lower confidence;
- shadow evaluation;
- additional evidence;

over unsafe adaptation.

---

# Decision Receipts

Autonomous decisions are designed to be auditable.

A decision receipt stores the information required to reconstruct what the system knew and what it decided.

Relevant information includes:

- decision ID;
- event/fingerprint ID;
- timestamp;
- market context;
- data freshness;
- regime state;
- drift state;
- eligible hypotheses;
- rejected/ineligible hypotheses;
- evidence;
- scores;
- selected hypothesis;
- `NO_TRADE` state where applicable;
- confidence;
- horizon;
- proposal information;
- risk result;
- execution result;
- eventual outcome.

The receipt is intended to make autonomous behavior observable without exposing internal chain-of-thought.

---

# Proposal Generation

The autonomous decision layer does not directly submit broker orders.

Once a decision is selected, the system produces a bounded proposal.

That proposal then enters the shared proposal/admission system.

The autonomous layer therefore decides:

> "This is the action I consider eligible."

It does not decide:

> "Ignore the rest of the system and send this order to the broker."

---

# Admission Layer

All autonomous proposals go through the common admission infrastructure.

This ensures autonomous activity participates in the same account-level coordination system used by other proposal sources.

The admission layer handles:

- proposal normalization;
- priority;
- scheduling;
- serialization;
- account-level coordination;
- provenance.

Autonomous trading therefore does not operate outside the existing execution controls.

---

# Shared Human + Autonomous Account

Human and autonomous activity can exist on the same account.

The autonomous system does not assume that it owns the account.

The system must account for:

- existing portfolio positions;
- buying power;
- portfolio exposure;
- simultaneous human actions;
- competing proposals;
- account serialization;
- conflicting exposure.

This is especially important when the human is interacting with the system at the same time the autonomous engine is operating.

---

# Priority Model

The project uses explicit proposal priorities so that different types of actions can coexist safely.

The current conceptual priority hierarchy includes:

- emergency reconciliation;
- human risk reduction;
- autonomous risk reduction;
- human new-risk actions;
- autonomous opportunity actions.

Autonomous opportunity generation therefore does not automatically outrank urgent account protection.

---

# Risk Engine

The Risk Engine remains the authoritative safety layer.

The autonomous layer does not replace the Risk Engine.

The Risk Engine evaluates the final structured proposal using authoritative account and market facts.

Current risk evaluation includes multiple deterministic gates covering areas such as:

- structural validity;
- data freshness;
- payoff constraints;
- drawdown;
- buying power;
- allocation;
- concentration;
- market regime;
- volatility;
- other project-defined safety requirements.

The autonomous layer is allowed to recommend.

The Risk Engine is allowed to say:

> NO.

---

# Fresh Authoritative Facts

A decision-layer context snapshot is not treated as permanent truth.

Immediately before risk evaluation, the worker/risk adapter refreshes the authoritative facts required by the Risk Engine.

This prevents stale decision information from becoming an execution authorization.

The system therefore separates:

**Decision context**

from:

**Final risk authority**

---

# CORE-X Execution

CORE-X is the controlled execution boundary.

Autonomous code cannot directly bypass it.

The expected execution path is:

Decision
→ Proposal
→ Admission
→ Risk Engine
→ CORE-X
→ Broker

CORE-X is responsible for the controlled dispatch behavior and execution state tracking.

The autonomous layer has no permission to replace CORE-X with direct broker calls.

---

# Execution States

Execution results are represented explicitly.

Important terminal and safety states include concepts such as:

- `SUCCEEDED`;
- `REJECTED`;
- `FAILED_SAFE`;
- `EXECUTION_UNCERTAIN`.

A broker/API `is_err=True` result is treated as:

**`REJECTED`**

because the tool was reached and the broker explicitly refused the action.

It is not treated as:

- successful execution;
- an unresolved execution;
- "never reached the broker."

This distinction is important for reconciliation and auditability.

---

# Execution Uncertainty

Execution uncertainty is treated differently from a known rejection.

If the system does not know whether a state-changing action completed successfully, the system can enter an uncertainty state.

In that situation:

- risky new actions are restricted;
- reads remain possible;
- reconciliation remains possible;
- execution state is checked against persistent records;
- the account can be safely recovered once the true state is known.

A known rejection does not create execution uncertainty.

---

# Reconciliation

The system includes reconciliation logic for uncertain execution states.

Reconciliation checks persistent execution information and determines whether an unresolved execution remains.

The system intentionally fails closed when unresolved execution state still exists.

The administrative reconciliation endpoint is protected under the admin namespace and produces warning/audit logging.

The endpoint must not silently remove uncertainty without evidence that it is safe to do so.

---

# Persistence

Important autonomous state is stored durably where needed.

Persistent information includes:

- decision records;
- execution journal information;
- mature outcomes;
- learning-related preference information.

Short-lived operational state may intentionally be recreated after restart, such as:

- dynamic discovery subscriptions;
- temporary fingerprints;
- in-flight runtime locks.

The system is designed so that important execution uncertainty and durable decision outcomes can be recovered.

---

# Fingerprinting and Deduplication

Every meaningful autonomous event is protected against repeated processing.

Fingerprinting is intended to prevent:

- duplicate decisions;
- repeated proposals;
- repeated execution attempts;
- event storms.

The fingerprint lifecycle is expected to move through:

**Acquire → Decision → Terminal Result → Release/Cooldown**

Terminal paths must correctly clean up or cool down fingerprints so a successful or rejected decision cannot permanently suppress future activity.

---

# Performance Model

The autonomous system is designed around different speeds of work.

## Fast Path

The fast path should remain lightweight.

Typical work:

- receive market event;
- normalize data;
- deterministic event filtering;
- fingerprinting;
- cached context;
- regime lookup;
- hypothesis eligibility;
- `NO_TRADE` or evidence request.

## Slow Path

Only qualified candidates should perform more expensive work.

Typical work:

- additional market/account facts;
- evidence collection;
- option analysis when relevant;
- decision receipt creation;
- bounded proposal generation;
- optional LLM evidence synthesis where actually needed.

Learning work should remain outside the hot market-event path.

---

# LLM Usage

The LLM is not the trading authority.

The system is intentionally designed so deterministic components handle continuous market activity.

The LLM should only be called when its interpretation adds real value.

The LLM must not:

- process every market tick;
- invent market facts;
- directly place orders;
- bypass Risk Engine;
- bypass CORE-X;
- change safety policies;
- generate arbitrary source-code changes;
- become the final execution authority.

Where used, the LLM is treated as bounded evidence synthesis, interpretation, or challenge.

Deterministic market facts remain authoritative.

---

# Live Activity Console

The live console is a deterministic observability layer.

It does not use an LLM to manufacture reasoning text.

The console is intended to display meaningful state transitions such as:

- autonomous discovery;
- market state changes;
- decision cycle opened;
- eligible hypotheses;
- evidence collected;
- hypothesis selected;
- `NO_TRADE`;
- confidence;
- risk allowed/blocked;
- execution result;
- reconciliation;
- mature outcomes;
- learning updates;
- drift/shadow state.

The console intentionally avoids:

- every raw quote;
- repetitive tick noise;
- internal chain-of-thought;
- unbounded model output.

The objective is to make autonomous behavior visible while remaining technically truthful.

---

# UI / Backend Event Flow

The backend publishes structured activity events.

The frontend subscribes through the activity streaming endpoint.

The UI renders structured metadata such as:

- event category;
- symbol;
- decision state;
- confidence;
- regime;
- hypothesis;
- risk result;
- execution state.

This makes the console an observability surface rather than a second autonomous agent.

---

# Error Handling

The autonomous system is designed to fail closed where safety or data certainty is insufficient.

Examples include:

- stale required evidence;
- missing critical facts;
- invalid proposal structure;
- risk rejection;
- unresolved execution;
- broker rejection;
- inconsistent data.

The desired response is not:

> Guess and continue.

The desired response is:

> Abstain, reject, defer, or reconcile safely.

---

# Options Support — Current State

The project already contains options-related infrastructure in the risk/execution side.

Existing options capabilities include concepts such as:

- option quote facts;
- options filtering;
- option structural validation;
- payoff risk checks;
- option proposal support;
- bounded option-related risk constraints.

However, these capabilities do not yet mean autonomous options decision-making is complete.

Currently the autonomous hypothesis registry is stock-focused.

Therefore the current system does not yet autonomously decide:

> "For this opportunity, an option is better than owning the stock."

That is the next major development phase.

---

# Planned Autonomous Options Capability

The intended future behavior is a unified decision process.

For a qualifying underlying:

**Market opportunity**

→ evaluate stock hypotheses  
→ evaluate eligible option hypotheses  
→ gather required evidence  
→ compare scores/confidence  
→ choose:

- STOCK
- OPTION
- `NO_TRADE`

If the system chooses an option, it should then:

1. identify the appropriate bounded option approach;
2. retrieve option data only when needed;
3. filter the available contracts;
4. select an eligible contract;
5. create a bounded option proposal;
6. send it through Admission;
7. send it through Risk Engine;
8. execute through CORE-X;
9. monitor the option outcome;
10. update option-related preference after a mature outcome.

The stock and option decisions should remain part of one autonomous decision intelligence system.

They should not become two unrelated autonomous bots.

---

# Options Design Principles

The future options implementation should NOT become a traditional fixed-rule options bot.

Avoid designs such as:

- bullish signal → always buy call;
- bearish signal → always buy put;
- volatility signal → always use one fixed contract;
- one hard-coded expiry;
- one hard-coded strike.

Instead, option decisions should depend on context and evidence.

Important considerations can include:

- underlying directional context;
- market regime;
- volatility regime;
- option liquidity;
- spread quality;
- expiration;
- strike distance;
- time horizon;
- contract quality;
- underlying movement;
- portfolio exposure;
- data freshness.

The system should be allowed to decide that:

- stock is better;
- option is better;
- both are unsuitable;
- `NO_TRADE` is best.

---

# Options Data Philosophy

The planned options implementation should remain underlying-first.

The system should not attempt to continuously monitor huge option chains.

Instead:

**Underlying opportunity**
→ determine whether option analysis is warranted
→ retrieve bounded option information
→ filter eligible contracts
→ evaluate contract quality
→ select the best eligible bounded candidate

This keeps data use, latency, and processing requirements manageable.

---

# Real Data Requirement

The intended production/autonomous path should use actual configured Alpaca data.

Production logic should never rely on:

- fake market prices;
- fake option quotes;
- fake liquidity;
- fabricated implied volatility;
- hard-coded contract selections;
- fake buying power;
- fake execution results.

Any test-only mock must remain isolated from production behavior.

The current system has already removed previously identified dead placeholder code from the autonomous pipeline.

---

# Testing Philosophy

Tests are used to verify deterministic behavior and safety boundaries.

Tests should prove:

- decision correctness;
- NO_TRADE behavior;
- learning behavior;
- regime/drift safeguards;
- fingerprint lifecycle;
- reconciliation;
- execution state semantics;
- risk isolation;
- API behavior;
- streaming behavior.

Tests should not be treated as proof of live-market profitability.

---

# Current Verified Hardening

Recent hardening addressed several infrastructure issues.

These include:

- moving blocking portfolio synchronization work off the asyncio event loop;
- preserving the 300-second default outcome horizon while allowing configuration;
- exposing autonomous status through a public controller snapshot;
- protecting reconciliation under an admin endpoint;
- preserving fail-closed uncertainty behavior;
- correcting `REJECTED` execution semantics;
- removing dead escalation/brief-builder components and orphaned model code;
- extending regression coverage.

The current hardening suite reports:

**17 tests passed**

with the third-party WebSocket deprecation warning remaining unrelated to application behavior.

---

# Current Test Coverage

The verified autonomous test coverage includes scenarios for:

- bounded adaptation;
- drift;
- decision recovery;
- duplicate suppression;
- `NO_TRADE`;
- reconciliation;
- risk blocking;
- stale evidence;
- LLM failure fallback;
- exposure safety;
- bounded options risk validation;
- broker rejection;
- rejection replay;
- rejection propagation;
- admin reconciliation;
- controller status snapshot;
- outcome-horizon configuration;
- async portfolio synchronization.

The full current test run completed successfully.

---

# What the System Can Do Today

Without the user manually selecting a stock during a market session, the autonomous stock engine can:

1. discover relevant moving equities;
2. add them to the monitoring universe;
3. observe their market activity;
4. detect a meaningful event;
5. open an autonomous decision cycle;
6. evaluate market context;
7. estimate regime;
8. compare bounded stock hypotheses;
9. select a stock action or `NO_TRADE`;
10. create a bounded proposal;
11. route the proposal through Admission;
12. apply the Risk Engine;
13. execute through CORE-X where permitted;
14. track the execution state;
15. evaluate the mature outcome;
16. update future hypothesis preference.

---

# What the System Does Not Yet Do

The current autonomous decision layer does not yet independently choose and execute options.

In particular, the current autonomous layer does not yet fully support:

- autonomous stock-vs-option competition;
- option-specific autonomous hypotheses;
- autonomous option contract selection inside the decision process;
- option-specific autonomous outcome learning.

Those are the next major implementation requirements.

---

# Future Unified Behavior

The intended final system behavior is:

The user starts the system.

The user does not manually choose an asset for every opportunity.

The autonomous engine observes the market.

It discovers a relevant underlying.

It builds context.

It determines the current market regime.

It evaluates possible approaches.

It gathers the evidence required for those approaches.

It decides whether the best action is:

**STOCK**

or:

**OPTION**

or:

**NO_TRADE**

It then creates a bounded proposal.

The proposal passes through:

**Admission → Risk Engine → CORE-X → Broker**

The system observes the resulting outcome.

The mature outcome is recorded.

The outcome updates the future decision preference conservatively.

This process repeats continuously while the system remains within its safety boundaries.

---

# Performance Evaluation

The project should not be evaluated using raw trade count alone.

It should not optimize only for short-term P&L.

Relevant performance dimensions include:

- total P&L;
- equity curve;
- drawdown;
- risk-adjusted return;
- tail losses;
- volatility;
- exposure;
- concentration;
- buying-power usage;
- turnover;
- execution quality;
- rejection rate;
- duplicate proposal rate;
- avoided bad trades;
- decision consistency;
- confidence calibration;
- autonomous observation quality;
- stock-vs-option decision quality once options autonomy is enabled.

The goal is strong overall system behavior, not maximum trading frequency.

---

# Paper Trading Limitations

Results produced in the paper environment should be treated as simulated trading evidence.

Paper trading does not perfectly reproduce all properties of live market execution.

Important limitations can include:

- market impact;
- queue position;
- latency effects;
- slippage behavior;
- price improvement;
- fees/dividends and other real execution differences.

Therefore:

> Strong paper performance is evidence of system behavior, not a guarantee of real-world trading performance.

---

# Safety Philosophy

The project follows a simple rule:

> Intelligence may adapt. Safety may not.

Autonomous decision-making can become more selective and context-aware.

But the system must not respond to poor performance by:

- increasing risk limits;
- bypassing risk checks;
- increasing execution authority;
- changing broker permissions;
- modifying CORE-X;
- rewriting source code;
- inventing new safety exemptions.

A losing strategy must become less preferred, not more powerful.

---

# Development Principles

The project prioritizes:

- deterministic safety;
- bounded autonomy;
- real market data;
- auditable decisions;
- conservative learning;
- low unnecessary latency;
- minimal LLM usage;
- laptop-friendly execution;
- explicit failure handling;
- reuse of existing components;
- no duplicate execution systems;
- no unnecessary infrastructure.

The goal is not maximum architectural complexity.

The goal is a system that is:

**autonomous, intelligent, explainable, testable, and safe.**

---

# Current Roadmap

## Completed

- Autonomous stock discovery
- Dynamic monitoring universe
- Market streaming
- Material event processing
- Deduplication/fingerprinting
- Context snapshots
- Regime estimation
- Drift handling
- Bounded stock hypotheses
- Contextual Bayesian selection
- `NO_TRADE`
- Decision receipts
- Admission system
- Account serialization
- Risk Engine integration
- CORE-X execution
- Execution uncertainty handling
- Reconciliation
- Outcome monitoring
- Persistent learning
- Live activity console
- Async hardening
- Rejected execution semantics
- Dead-code cleanup
- Autonomous hardening tests

## Next Major Milestone

### Autonomous Options Decision Intelligence

Implement options inside the same decision controller so the final system can autonomously decide:

**STOCK vs OPTION vs NO_TRADE**

while preserving all existing stock behavior and all immutable Risk/CORE-X protections.

The options implementation should:

- use real Alpaca data;
- reuse existing options infrastructure;
- remain bounded;
- avoid giant option-chain scans;
- avoid unnecessary LLM calls;
- support contract selection;
- support option-specific outcomes;
- support conservative learning;
- integrate with the existing Risk → CORE-X path;
- remain one unified autonomous system.

---

# Final Project Definition

This project is an autonomous AI trading system for US equities and options that combines:

- continuous deterministic market observation;
- autonomous discovery;
- bounded adaptive decision intelligence;
- market-regime awareness;
- evidence-driven selection;
- explicit abstention;
- deterministic risk enforcement;
- controlled execution;
- reconciliation;
- outcome evaluation;
- conservative learning;
- human + autonomous account coordination;
- real-time deterministic observability.

The final objective is not to build an AI that blindly trades.

The objective is to build an AI trading system that can independently determine:

> **What opportunity exists?**

> **What evidence supports it?**

> **Which bounded approach is most appropriate?**

> **Is STOCK, OPTION, or NO_TRADE the best decision?**

> **Is the proposed action actually allowed by the risk system?**

> **What happened after the decision?**

> **What should the system prefer in a similar situation next time?**

while keeping execution authority and safety controls deterministic and immutable.