Inspiration

The rapid growth of generative AI is exciting, but it comes with a hidden cost: an enormous carbon footprint. Training GPT-sized models consumes as much energy as powering a U.S. household for decades, and every user query adds up. We asked ourselves: What if every AI interaction could automatically become greener without sacrificing quality? That question—and the challenge of aligning AI with sustainability goals—inspired EcoAI.

What it does

Rewrites prompts to reduce tokens while preserving intent.

Prunes unnecessary context in retrieval-augmented generation.

Streamlines multi-agent workflows by merging redundant steps.

Routes inference to low-carbon regions or greener times.

Generates Carbon Receipts showing tokens, energy, and CO₂ saved.

How we built it

SDK Core: TypeScript package wrapping OpenAI-style clients. Implements prompt compression, RAG context pruning, workflow DAG optimization, caching, and carbon-aware routing.

ML Monitoring: Embedding-based semantic similarity to validate prompt quality; MMR algorithm to select context; confusion matrix to measure parity.

Carbon Math: Token → FLOPs → Joules → kWh → CO₂ estimation based on research like CodeCarbon and Zeus.

Prompt Studio: HTML/CSS/JS web app inspired by ChatGPT UI, showing optimized prompts and receipts in real time.

Portal: Heroku-hosted backend with Postgres to store receipts and visualize per-user or per-organization CO₂ savings.

Challenges we ran into

Designing prompt compression that saved tokens without altering meaning.

Balancing engineering scope: building both a user-facing app and a developer SDK in hackathon time.

Estimating CO₂ accurately given uncertainty in model FLOPs and energy intensity.

Implementing a clean UI that felt intuitive, like ChatGPT, but added sustainability insights.

Accomplishments that we're proud of

Partnerships with Eco-Conscious Companies

We plan to collaborate with organizations that actively care about sustainability and are committed to reducing their carbon footprint.

By integrating EcoAI into their AI workflows, these companies can not only lower emissions but also showcase measurable climate impact to customers and investors.

EcoPoints Rewards System

Every token saved and every gram of CO₂ avoided will earn users EcoPoints inside the app.

EcoPoints can be redeemed for discounts, coupons, and perks from partner companies that align with environmental values.

Example: A user optimizes prompts and collects enough EcoPoints to get 10% off from a green travel company, sustainable fashion brand, or plant-based food service.

Gamified Sustainability Engagement

Introduce leaderboards, streaks, and badges for consistent users.

Reward both individuals and organizations that achieve milestones (e.g., “1000g CO₂ saved”).

This makes sustainability not just impactful but also engaging and rewarding.

Enterprise-Grade Expansion

Provide ESG dashboards for organizations so they can track AI-related emissions reductions alongside other sustainability metrics.

Offer compliance-ready reporting for Net Zero disclosures.

What we learned

How cutting-edge research (SPROUT, Clover, Zeus) can be translated into practical developer tools.

That prompt engineering + ML monitoring can meaningfully reduce emissions without hurting quality.

How important transparency is—users care when they see their carbon savings quantified.

What's next for our project

Integrating with real carbon-intensity APIs like ElectricityMaps and WattTime.

Expanding SDK support to Anthropic, Google Gemini, and open-source LLMs.

Offering enterprise dashboards for ESG reporting.

Packaging Prompt Studio as a browser extension so sustainability insights show up anywhere users type prompts.
