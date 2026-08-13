# Measuring what prompt optimization actually saves

A technical report on EcoAI's carbon model: the problem it's built for, what
it does, and a real-hardware experiment that found a limit in its own core
assumption.

*Originally built for HackMIT 2025, where it placed 1st in Infosys's Diamond
Sponsor track. This report and the codebase behind it were substantially
reworked afterward — see the commit history for what changed and why.*

---

## The problem

Data center electricity demand tied to AI and cryptocurrency is on a steep
trajectory. The International Energy Agency's *Electricity 2024* report
put AI and data center consumption at roughly 460 TWh in 2022 and projected
it toward 620–1,050 TWh by 2026 — the upper end comparable to Japan's entire
electricity consumption
[[IEA, Electricity 2024](https://www.iea.org/reports/electricity-2024)].
Training gets the attention, but for a widely-deployed model, cumulative
inference — billions of requests over the model's lifetime — is the larger
share of that footprint. That's the part every API call anyone makes
contributes to, and it's also the part with essentially no visibility: no
major LLM API returns an energy or carbon figure with its response.

Developers who want to reduce that footprint are left estimating. The tools
that actually *measure* it — Zeus (Chung, Liu, Xie & Chowdhury, NSDI 2023,
University of Michigan / ml-energy lab) and CodeCarbon read real power draw
off the GPU running inference, via NVML or RAPL. Both require access to that
hardware. If you're calling a hosted API, you don't have it — only the
provider does. That gap is the actual reason token-count-based estimation
exists as a category: it's what's available when you can't instrument the
chip.

## What EcoAI does

Two independent things, and it's worth being precise about which is which:

**Token and cost savings are exact.** The optimizer ([ecoai/services/optimizer.py](ecoai/services/optimizer.py))
rewrites a prompt, protecting code blocks, URLs, and template placeholders
from modification, and reports a `retention_score` — the fraction of content
words, numbers, and protected spans that survived — computed from the actual
before/after text, not asserted as a constant. Whatever it removes, the token
count and the dollar cost at published API prices ([ecoai/services/pricing.py](ecoai/services/pricing.py))
are counted directly. Nothing about that is a model.

**Energy and CO₂e are a formula**, not a measurement
([ecoai/services/carbon.py](ecoai/services/carbon.py)):

```
tokens → FLOPs → joules → kWh → grams CO₂e
```

FLOPs per token follows the standard `2 × active_parameters` transformer
estimate from Kaplan et al., *Scaling Laws for Neural Language Models*
[[arXiv:2001.08361](https://arxiv.org/abs/2001.08361)]. Joules per FLOP is
set from published accelerator throughput-per-watt figures. PUE and grid
carbon intensity are configurable, with a static per-region table. Every
coefficient is overridable through the environment, and none of it claims to
be a measurement of any specific request.

## The experiment

The formula implies something specific: fewer tokens in, proportionally
less energy. That's testable, so we tested it.

**Setup:** an NVIDIA L4 GPU (Google Compute Engine, on-demand), running
Qwen2.5-1.5B-Instruct through [vLLM](https://github.com/vllm-project/vllm).
Generation was wrapped in Zeus's `ZeusMonitor`, which samples real GPU power
through NVML during the call — not estimated, read off the chip. Two runs:
the same request, once with the original prompt and once with EcoAI's
optimized version.

**Finding:** measured energy barely differed between the two. The reason is
structural, not incidental to this one run: generation used a fixed
`max_tokens` cap, and autoregressive decoding — producing the output, one
token at a time — costs real GPU energy per output token, independent of how
long the input was. Shortening the prompt only shrinks the one-time prefill
pass over the input, which is a small fraction of a typical request's total
compute next to a capped or long output. The formula's linear
`tokens → joules` relationship doesn't distinguish input tokens from output
tokens; a real GPU does, and the difference is large enough to matter for
exactly the use case — chat and completion-style requests — this tool is
built for.

**What still holds:** relative comparisons at fixed token count. A larger
model costing more energy per token, or the same request costing less in a
lower-carbon-intensity region, is true by construction of the arithmetic —
it doesn't need empirical validation, and the experiment didn't touch it.
What it does show is that "shorter prompt → proportionally less energy" is
the wrong inference to draw from that same arithmetic for output-heavy
requests. Input-token reduction is still real and still worth having — it's
exactly and directly counted, and on any workload with long, repeated, or
templated prompts and short outputs, prefill is not negligible. It just
isn't the same claim as "this reduced this request's measured energy," which
is what a formula this simple would suggest if you didn't check.

## Why this is worth documenting rather than smoothing over

Every carbon-accounting tool built on token counting alone — and most of
them are — is making the same implicit assumption this one made until it
was checked against a real GPU. A tool that reports a shrinking CO₂ number
every time it shortens a prompt, without that number reflecting what
actually happened on the hardware, produces reporting that looks precise
and isn't. Given that the entire premise of a project like this is
providing visibility into a real environmental cost, publishing a formula
uncorrected by the one check available — real hardware, real measurement
tooling, a direct comparison — would defeat the point.

Full scope, setup instructions, and API reference: [README.md](README.md#how-the-carbon-estimate-works-and-how-far-you-can-trust-it).
