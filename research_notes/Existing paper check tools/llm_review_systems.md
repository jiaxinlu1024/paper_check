# LLM-based automated paper review, reviewer simulation, and error-finding benchmarks (state as of 2026-10-17)

Method and caveats for the report writer: arXiv, ACL Anthology, OpenReview, vendor sites (refine.ink, paperreview.ai, qed.science, reviewer3.com), Nature, conference blogs and RePEc were all unreachable from this session, so their content comes from WebSearch result summaries. Repository facts (prompts, licenses, architectures, benchmark tables) were read directly from GitHub raw files and are the most reliable items here. The shared web-search budget ran out before I could cover a few items; they are listed under Gaps. Evidence labels used below: **[PR]** peer-reviewed publication; **[PP]** preprint or working paper, not peer reviewed as far as I found; **[VR]** official venue report or blog; **[SR]** self-reported by the developer or vendor, i.e. marketing; **[2nd]** secondary coverage; **[CODE]** read directly in the repository. Several product "reviews" come from Manusights, a competing paid service, so treat those as biased.

## Q1. Which systems exist, and how does each work? (one record per system)

### Takeaway
About 30 relevant systems exist. They fall into five groups. (1) Research reviewers that write whole reviews: Liang et al., MARG, Sakana's reviewer, OpenReviewer, CycleReviewer, DeepReviewer, ReviewerToo, the Stanford Agentic Reviewer and ProReviewer. Most are tuned to ML conference papers and judged by score or decision agreement, not by errors found. (2) Venue deployments: the NeurIPS 2024 checklist assistant, the ICLR 2025 review-feedback agent, the AAAI-26 AI reviews and Google's PAT at STOC, ICML and NeurIPS 2026. (3) Closed commercial error checkers: Refine, q.e.d., Reviewer3, YesNoError and IsItCredible. Only Refine is aimed at economics. (4) Open-source error finders and Claude Code skills: OpenAIReview, coarse, Claes Bäckman's economics review skills, academic-research-skills, OpenJudge and the Black Spatula Project. (5) Simulation of review dynamics: AgentReview. Bäckman's MIT-licensed Claude Code skills for economics papers and OpenAIReview's MIT-licensed prompts and skill are the closest prior art to the team's DESIGN.md.

### Cited Findings

#### 1.1 Research reviewers that write whole reviews

**Liang et al. 2023 (Stanford, Zou lab): GPT-4 feedback on research papers.** Evidence: [PP] (arXiv), [CODE].
- Links: paper [arXiv 2310.01783](https://arxiv.org/abs/2310.01783); code [github.com/Weixin-Liang/LLM-scientific-feedback](https://raw.githubusercontent.com/Weixin-Liang/LLM-scientific-feedback/HEAD/README.md); product: an "AI Feedback on Research Manuscripts" GPT in the OpenAI GPT Store — [README](https://raw.githubusercontent.com/Weixin-Liang/LLM-scientific-feedback/HEAD/README.md).
- How it works: a single GPT-4 call on text parsed by the ScienceBeam PDF parser. The prompt concatenates the abstract, the figure and table captions and the main content, truncated to 6,500 tokens. It asks for a "review outline" with four parts: 1 significance and novelty; 2 potential reasons for acceptance; 3 potential reasons for rejection, as 4 reasons with at least 2 sub-bullets each; 4 suggestions for improvement, 4 items. There is no chunking beyond truncation and no retrieval — [main.py](https://raw.githubusercontent.com/Weixin-Liang/LLM-scientific-feedback/HEAD/main.py).
- Evaluation and accuracy: the authors compared GPT-4 comments with human reviews on 3,096 papers from 15 Nature-family journals and 1,709 ICLR papers. GPT-4–human overlap was 30.85% for Nature and 39.23% for ICLR. Human–human overlap was 28.58% and 35.25%. Overlap was higher for weaker papers: 43.80% for rejected ICLR papers. In a prospective study of 308 researchers from 110 US institutions, 57.4% found the feedback helpful or very helpful. 82.4% found it more beneficial than feedback from at least some human reviewers — [README](https://raw.githubusercontent.com/Weixin-Liang/LLM-scientific-feedback/HEAD/README.md).
- Weaknesses the authors report: GPT-4 "tends to focus on certain aspects of scientific feedback (e.g., 'add experiments on more datasets'), and often struggles to provide in-depth critique of method design" — [README](https://raw.githubusercontent.com/Weixin-Liang/LLM-scientific-feedback/HEAD/README.md).
- License: CC BY 4.0 — [LICENSE](https://raw.githubusercontent.com/Weixin-Liang/LLM-scientific-feedback/HEAD/LICENSE).

**ReviewerGPT (Liu and Shah 2023, CMU).** Evidence: [PP].
- Links: [arXiv 2306.00622](https://arxiv.org/pdf/2306.00622). I found no code.
- How it works: GPT-4 is given separate, targeted prompts for three tasks.
  - Error finding: 13 short CS papers, each with one deliberately inserted error. GPT-4 found errors in 7 of the 13, both mathematical and conceptual.
  - Checklist verification: 16 closed-ended questions across 15 NeurIPS 2022 papers, 119 question–paper pairs, with 3 queries per pair and a majority vote. Accuracy was 86.6%, the same as the agreement of author-submitted checklists with the ground truth.
  - Picking the better abstract from 10 pairs: GPT-4 was wrong on 6 of 10.
  - The authors conclude that LLMs are promising "for specific reviewing tasks, but not (yet) for complete evaluations" — [arXiv via search](https://arxiv.org/pdf/2306.00622).
- The later FLAWS benchmark cites this study as showing that GPT-4 does better when prompted specifically to find errors than when asked for a holistic review — [FLAWS](https://arxiv.org/html/2511.21843v1).

**MARG: Multi-Agent Review Generation (D'Arcy, Hope, Birnbaum, Downey; Allen AI and Northwestern).** Evidence: [PP], [CODE].
- Links: [arXiv 2401.04259](https://arxiv.org/pdf/2401.04259); code [github.com/allenai/marg-reviewer](https://raw.githubusercontent.com/allenai/marg-reviewer/HEAD/README.md); [D'Arcy thesis](https://www.mccormick.northwestern.edu/computer-science/documents/mike-d-arcy-thesis.pdf).
- How it works:
  - GPT-4-0613. The paper is split into 4,096-token chunks, one worker agent per chunk.
  - A leader agent coordinates the workers through a "SEND MESSAGE" protocol. Workers can talk only to the leader.
  - MARG-S adds expert agents for three comment families: `experiments_proofs`, `novelty_impact` and `clarity_reproducibility`.
  - Each draft comment then goes through a refine prompt. That prompt may set the comment to null "if you think the comment is not good enough to include in a review".
  - Output is a JSON list of comment strings — [review_prompts.json](https://raw.githubusercontent.com/allenai/marg-reviewer/HEAD/review_worker/review_prompts.json); [multi_agent.py](https://raw.githubusercontent.com/allenai/marg-reviewer/HEAD/review_worker/aries/review_generation/multi_agent.py).
  - No retrieval of related work.
- Evaluation and accuracy: a user study with 9 NLP and HCI researchers and mixed-effects analysis. MARG cut generic comments from 60% to 29% and produced 3.7 "good" comments per paper, 2.2x the best baseline's 1.7 — [arXiv abstract via search](https://arxiv.org/pdf/2401.04259). D'Arcy's thesis gives 1.5 for the baseline — [thesis](https://www.mccormick.northwestern.edu/computer-science/documents/mike-d-arcy-thesis.pdf). The repository also reproduces automatic alignment with human reviews on the ARIES dataset — [README](https://raw.githubusercontent.com/allenai/marg-reviewer/HEAD/README.md).
- Maturity: research demo run with Docker. It bundles baselines SARG-B ("barebones") and Liang et al. ("LiZCa") — [README](https://raw.githubusercontent.com/allenai/marg-reviewer/HEAD/README.md).
- License: Apache-2.0 — [README](https://raw.githubusercontent.com/allenai/marg-reviewer/HEAD/README.md).

**Sakana "The AI Scientist" Automated Reviewer.** Evidence: [PP] v1; [PR] Nature 2026 version; [CODE].
- Links: [arXiv 2408.06292](https://arxiv.org/pdf/2408.06292); Nature version announced at [sakana.ai/ai-scientist-nature](https://sakana.ai/ai-scientist-nature/); code [github.com/SakanaAI/AI-Scientist](https://raw.githubusercontent.com/SakanaAI/AI-Scientist/HEAD/README.md) and [AI-Scientist-v2](https://raw.githubusercontent.com/SakanaAI/AI-Scientist-v2/HEAD/README.md).
- How it works: one LLM (the README says reviews are "best done with GPT-4o") reviews against the NeurIPS review form. It writes THOUGHT notes, then JSON with these fields:
  - Summary, Strengths, Weaknesses
  - Originality, Quality, Clarity and Significance, each rated 1–4
  - Questions, Limitations, and Ethical Concerns as a boolean
  - Soundness, Presentation and Contribution, each rated 1–4
  - Overall (1–10), Confidence (1–5), and a Decision of Accept or Reject only
- Text extraction and options:
  - Text comes from pymupdf4llm, falling back to pymupdf and then pypdf. The whole text goes into one prompt, with no chunking and no retrieval.
  - Options: N few-shot examples, N self-reflection rounds ("If there is nothing to improve... include 'I am done'"), and an ensemble of N reviews at temperature 0.75.
  - An "Area Chair" prompt merges the ensemble into a meta-review, and numeric scores are replaced by the ensemble mean.
  - The default system prompt is the negative variant: "If a paper is bad or you are unsure, give it bad scores and reject it" — [perform_review.py](https://raw.githubusercontent.com/SakanaAI/AI-Scientist/HEAD/ai_scientist/perform_review.py).
  - The benchmark command uses 5 reflections, 5 ensemble reviews, 1 few-shot example and temperature 0.1 on 500 papers — [README](https://raw.githubusercontent.com/SakanaAI/AI-Scientist/HEAD/README.md).
- Evaluation and accuracy (500 ICLR 2022 papers, accept/reject):
  - Humans: balanced accuracy 0.66, F1 0.49, AUC 0.65. GPT-4o zero-shot: balanced accuracy 0.61, F1 0.43 — [arXiv 2408.06292 via search](https://arxiv.org/pdf/2408.06292).
  - The final configuration reached about 70% accuracy against 73% for humans, and F1 0.57 against 0.49 — [arXiv 2408.06292 via secondary summary](https://arxiv.org/pdf/2408.06292).
  - Ablation: reflection and one-shot prompting each added about 2%. Ensembling "does not appear to improve the reviewer's performance substantially but can reduce variance" — [arXiv 2408.06292](https://arxiv.org/pdf/2408.06292).
  - Conflict: the oft-quoted "balanced accuracy 0.65 versus 0.66 for humans" for the final configuration could not be confirmed. One search summary attributed 0.65 to the human AUC instead.
  - Nature (2026) version: balanced accuracy 69% on papers from before the model's knowledge cutoff, F1 0.62, and 66% on 2025 papers after the cutoff — [Sakana](https://sakana.ai/ai-scientist-nature/); [Warp News](https://www.warpnews.org/artificial-intelligence/ai-scientist-produces-increasingly-better-papers-and-an-ai-system-can-review-them-as-well-as-humans/).
  - The follow-up "Towards End-to-End Automation of AI Research" found o4-mini with a 5-review ensemble and meta-review best overall — [arXiv 2606.15497](https://arxiv.org/pdf/2606.15497).
  - The v2 system produced "the first workshop paper written entirely by AI and accepted through peer review" — [v2 README](https://raw.githubusercontent.com/SakanaAI/AI-Scientist-v2/HEAD/README.md).
- License: the "AI Scientist Source Code License" v1.0 (Dec 2025), based on the Responsible AI Source Code License. Clause 3(e) prohibits generating or disseminating manuscripts without a prominent disclaimer that they are machine-generated. The restrictions must be carried into any downstream agreement — [LICENSE](https://raw.githubusercontent.com/SakanaAI/AI-Scientist/HEAD/LICENSE).
- Independent critique exists: Beel et al., "Evaluating Sakana's AI Scientist: Bold Claims, Mixed Results, and a Promising Future?" — [arXiv 2502.14297](https://arxiv.org/pdf/2502.14297). I could not read its content.

**OpenReviewer (Idahl and Ahmadi; NAACL 2025 demo).** Evidence: [PR].
- Links: [ACL Anthology 2025.naacl-demo.44](https://aclanthology.org/2025.naacl-demo.44); [arXiv 2412.11948](https://arxiv.org/pdf/2412.11948); code [github.com/maxidl/openreviewer](https://raw.githubusercontent.com/maxidl/openreviewer/HEAD/README.md); the Llama-OpenReviewer-8B model and a demo are on Hugging Face — [README](https://raw.githubusercontent.com/maxidl/openreviewer/HEAD/README.md).
- How it works: Llama-3.1-8B-Instruct, fully fine-tuned for 3 epochs with a 128k-token context on 79,000 high-confidence reviews from ICLR and NeurIPS 2022–2025. Its 36,000 papers were converted to Markdown with Marker. It runs a single pass that fills a conference template (ICLR 2025 by default), with no retrieval. Training took 34 hours on 64 A100s — [README](https://raw.githubusercontent.com/maxidl/openreviewer/HEAD/README.md).
- Evaluation: on 400 test papers its reviews were "more critical and realistic" than GPT-4's and Claude-3.5's. General LLMs skewed toward overly positive recommendations, while OpenReviewer's matched the human rating distribution more closely — [abstract via search](https://arxiv.org/pdf/2412.11948v1). I could not retrieve numeric agreement scores.
- License: there is no LICENSE file at the repository root. The model license was not verified — [CODE probe](https://raw.githubusercontent.com/maxidl/openreviewer/HEAD/README.md).

**CycleReviewer / CycleResearcher (Weng et al., WestlakeNLP; ICLR 2025).** Evidence: [PR].
- Links: [arXiv 2411.00816](https://arxiv.org/pdf/2411.00816); [ICLR 2025 poster](https://iclr.cc/virtual/2025/poster/32074); [slides](https://iclr.cc/media/iclr-2025/Slides/32074.pdf).
- How it works: a reviewer model trained on Review-5k (4,991 papers with more than 16,000 reviewer comments). It generates reviews and scores that serve as the reward for the CycleResearcher paper-writing model — [slides via search](https://iclr.cc/media/iclr-2025/Slides/32074.pdf).
- Accuracy: 26.89% lower mean absolute error in score prediction than individual human reviewers, and 74.24% decision accuracy for CycleReviewer-123B — [arXiv/slides via search](https://arxiv.org/pdf/2411.00816).
- License: the "CycleResearcher License", based on the Mistral AI Research License. Users must register an academic affiliation and research purpose. Commercial use is prohibited, AI assistance must be disclosed, and "commercial paper generation services" are banned — [LICENSE.md](https://raw.githubusercontent.com/zhu-minjun/Researcher/HEAD/LICENSE.md).

**DeepReview / DeepReviewer (Zhu et al.; ACL 2025).** Evidence: [PR].
- Links: [ACL 2025 long 1420](https://aclanthology.org/2025.acl-long.1420); [arXiv 2503.08569](https://arxiv.org/pdf/2503.08569).
- How it works: DeepReview-13K was built by a pipeline whose first stage is novelty verification, with three components: question generation, paper analysis and literature review. DeepReviewer-14B was trained on it and has several inference modes — [search summary of arXiv 2503.08569](https://arxiv.org/pdf/2503.08569).
- Accuracy: DeepReviewer-14B beats CycleReviewer-70B on rating MSE, rating Spearman and paper-selection accuracy while using fewer tokens. LLM-judged win rates were 88.21% against GPT-o1 and 80.20% against DeepSeek-R1 — [arXiv 2503.08569](https://arxiv.org/pdf/2503.08569).
- License: it comes from the same WestlakeNLP group, whose "Researcher" repository uses the non-commercial CycleResearcher License — [LICENSE.md](https://raw.githubusercontent.com/zhu-minjun/Researcher/HEAD/LICENSE.md). Terms specific to DeepReviewer were not verified.

**ReviewerToo (Sahu, Larochelle, Charlin, Pal; Mila; Oct 2025).** Evidence: [PP].
- Links: [arXiv 2510.08867](https://arxiv.org/pdf/2510.08867).
- Accuracy: on 1,963 ICLR 2025 submissions, gpt-oss-120b reached 81.8% accuracy on binary accept/reject, against 83.9% for the average human reviewer. An LLM judge rated its reviews above the human average but below the best expert reviews.
- Strengths and weaknesses: strong on fact-checking and literature coverage; weak on methodological novelty and theoretical contributions — [arXiv 2510.08867 via search](https://arxiv.org/pdf/2510.08867).

**Stanford Agentic Reviewer (paperreview.ai; Yixing Jiang and Andrew Ng).** Evidence: [SR].
- Links: product and [tech overview](https://paperreview.ai/tech-overview); coverage at [36Kr](https://eu.36kr.com/en/p/3567973371935617/) and [HowAIWorks](https://howaiworks.ai/blog/paperreview-ai-stanford-agentic-reviewer-2025).
- How it works: an agent that grounds the review in related work it retrieves from arXiv. It was modified to output a 1–10 score by training on public ICLR 2025 reviews. English only. It works best in fields such as AI where papers are freely posted on arXiv — [tech overview via search](https://paperreview.ai/tech-overview); [HowAIWorks](https://howaiworks.ai/blog/paperreview-ai-stanford-agentic-reviewer-2025). The user uploads a PDF, gives an email address and an optional target venue, and receives the review by email — [Manusights, a competitor](https://manusights.com/blog/paperreview-ai-review-2026).
- Accuracy (self-reported): Spearman 0.42 between the AI and one human reviewer, against 0.41 between two humans, on ICLR 2025 — [tech overview](https://paperreview.ai/tech-overview). Usage: more than 21,500 papers from 160 countries in its first week; 95% of users found it useful and 91% found it actionable — [HowAIWorks](https://howaiworks.ai/blog/paperreview-ai-stanford-agentic-reviewer-2025).
- Terms: free. I found no code release.

**ProReviewer (Fang, Feng, Gurevych; UKP; June 2026).** Evidence: [PP].
- Links: [arXiv 2606.13349](https://arxiv.org/pdf/2606.13349).
- How it works: review is framed as active investigation, a Markov decision process, guided by a structured "review log" that tracks evidence. The 8B model is built on Qwen3-8B, trained with supervised fine-tuning and then reinforcement learning on ICLR 2025 data.
- Accuracy: up to 39% better than prompt-based frontier-LLM methods averaged over five quality dimensions, including actionability, grounding, technical depth and verifiability. It also had the highest win rates in human evaluation — [arXiv 2606.13349 via search](https://arxiv.org/pdf/2606.13349).
- License: MIT for the model card — [Friendli model page](https://friendli.ai/models/UKPLab/ProReviewer-8B).

#### 1.2 Simulation of review dynamics

**AgentReview (Jin et al.; EMNLP 2024).** Evidence: [PR], [CODE].
- Links: [ACL Anthology 2024.emnlp-main.70](https://aclanthology.org/2024.emnlp-main.70/); [arXiv 2406.12708](https://arxiv.org/abs/2406.12708v2); code [github.com/Ahren09/AgentReview](https://raw.githubusercontent.com/Ahren09/AgentReview/HEAD/README.md).
- How it works: a five-phase simulated review process with reviewer, author and area-chair agents whose traits are set by prompt. Reviewers vary by commitment (responsible or irresponsible), among other traits; area chairs are authoritarian, conformist or inclusive. It generated more than 53,800 review documents — [README](https://raw.githubusercontent.com/Ahren09/AgentReview/HEAD/README.md).
- Findings:
  - 37.1% of the variation in paper decisions is due to reviewer biases — [ACL Anthology](https://aclanthology.org/2024.emnlp-main.70/).
  - Social influence cut the standard deviation of ratings by 27.2% after rebuttals.
  - One under-committed reviewer cut commitment by 18.7% across all reviewers.
  - Revealing author identity for just 10% of papers shifted 27.7% of decisions.
  - The rebuttal phase had minimal effect on outcomes — [README](https://raw.githubusercontent.com/Ahren09/AgentReview/HEAD/README.md).
- License: Apache-2.0 (copyright ChatArena) — [LICENSE](https://raw.githubusercontent.com/Ahren09/AgentReview/HEAD/LICENSE).

#### 1.3 Venue deployments

**NeurIPS 2024 LLM author checklist assistant (Goldberg, Ullah et al.).** Evidence: [VR], [PP], [CODE].
- Links: [NeurIPS blog, 2024-12-10](https://blog.neurips.cc/2024/12/10/results-of-the-neurips-2024-experiment-on-the-usefulness-of-llms-as-an-author-checklist-assistant-for-scientific-papers/); [arXiv 2411.03417](https://arxiv.org/html/2411.03417v2); [Peer Review Congress abstract](https://peerreviewcongress.org/abstract/use-of-an-llm-as-an-author-checklist-assistant-for-scientific-papers-neurips-2024-experiment/); code [github.com/ihsaan-ullah/neurips-checklist-assistant](https://raw.githubusercontent.com/ihsaan-ullah/neurips-checklist-assistant/HEAD/README.md).
- How it works: one call per checklist question. Each call gets the question, the author's answer, the author's justification, the NeurIPS guidelines and the paper. The model must "identify any discrepancies with the actual 'Paper' content" and give itemized, actionable feedback with a score — [Sample prompt](https://raw.githubusercontent.com/ihsaan-ullah/neurips-checklist-assistant/HEAD/SamplePrompt/README.md). Settings: gpt-4-turbo-preview, temperature 1, at most 1,000 output tokens, the paper capped at about 15,000 words, and up to 3 retries per question — [assistant.py](https://raw.githubusercontent.com/ihsaan-ullah/neurips-checklist-assistant/HEAD/SampleCode/assistant.py). The repository also has "Adversarial LLM" notebooks for iterative attacks on checklist answers — [AdversarialLLM README](https://raw.githubusercontent.com/ihsaan-ullah/neurips-checklist-assistant/HEAD/AdversarialLLM/README.md).
- Results:
  - 234 papers submitted; 539 pre-use and 78 post-use survey responses.
  - More than 70% of authors found it useful, and 70% said they would revise.
  - The most common problems authors flagged were inaccuracy (20 of 52) and excessive strictness (14 of 52).
  - Positive ratings for "Useful" and "Excited to Use" dropped significantly after use.
  - The authors say it "should likely not be used as a fully automated review tool" — [arXiv 2411.03417 via search](https://arxiv.org/html/2411.03417v2); [NeurIPS blog](https://blog.neurips.cc/2024/12/10/results-of-the-neurips-2024-experiment-on-the-usefulness-of-llms-as-an-author-checklist-assistant-for-scientific-papers/).
- License: MIT — [LICENSE](https://raw.githubusercontent.com/ihsaan-ullah/neurips-checklist-assistant/HEAD/LICENSE).

**ICLR 2025 Review Feedback Agent (Thakkar, Yuksekgonul, Zou et al.).** Evidence: [VR], [PP], [CODE]. It gives feedback on reviews, not on papers.
- Links: [ICLR blog, 2025-04-15](https://blog.iclr.cc/2025/04/15/leveraging-llm-feedback-to-enhance-review-quality/); [arXiv 2504.09737](https://arxiv.org/pdf/2504.09737); code [github.com/zou-group/review_feedback_agent](https://raw.githubusercontent.com/zou-group/review_feedback_agent/HEAD/README.md).
- How it works:
  - The default architecture is `Actor(2)->Aggregator->FeedbackCritic->Formatter`: two independent actor calls, a merge step, a critic and a formatter — [feedback_agent.py](https://raw.githubusercontent.com/zou-group/review_feedback_agent/HEAD/review_feedback_agent/agents/feedback_agent.py).
  - The README initializes it with Claude Sonnet 3.5 — [README](https://raw.githubusercontent.com/zou-group/review_feedback_agent/HEAD/README.md).
  - It targets vague or unjustified review comments, misreadings of the paper and unprofessional remarks — [arXiv via search](https://arxiv.org/pdf/2504.09737).
  - Four LLM-judged "reliability tests" act as guardrails, and feedback is sent only if all four pass — [reliability_tests.py](https://raw.githubusercontent.com/zou-group/review_feedback_agent/HEAD/review_feedback_agent/tests/reliability_tests.py); [arXiv via search](https://arxiv.org/pdf/2504.09737):
    - `praise_feedback`: no feedback item merely praises.
    - `addressed_to_author`: no item is addressed to the authors.
    - `restate_reviewer`: no item just restates the reviewer.
    - `comments_in_review`: every quoted reviewer comment appears verbatim in the review.
- Results:
  - The randomized study ran from 15 Oct to 12 Nov 2024 and gave feedback on more than 20,000 reviews, half of all ICLR 2025 reviews.
  - 26.6% of reviewers who got feedback updated their reviews, incorporating 12,222 suggestions.
  - Blinded researchers rated the revised reviews more informative and clearer — [arXiv via search](https://arxiv.org/pdf/2504.09737); [ICLR blog](https://blog.iclr.cc/2025/04/15/leveraging-llm-feedback-to-enhance-review-quality/).
  - Count conflict: the blog cites 18,946 reviews receiving feedback, with groups of 22,467 (feedback) and 22,364 (control).
- License: MIT — [LICENSE](https://raw.githubusercontent.com/zou-group/review_feedback_agent/HEAD/LICENSE).

**AAAI-26 AI review pilot (Biswas and 12 co-authors; report dated 2026-04-15).** Evidence: [PP] venue report; parts [2nd].
- Links: [arXiv 2604.13940](https://arxiv.org/pdf/2604.13940); [AAAI announcement](https://aaai.org/aaai-launches-ai-powered-peer-review-assessment-system/); [36Kr coverage](https://eu.36kr.com/en/p/3773078234268168).
- How it works: every main-track paper received one clearly labeled AI review, 22,977 papers in under a day. The reviews carried no scores and no accept or reject recommendation, and replaced no human reviewer. The system is a multi-stage pipeline combining frontier models, OCR, tool-augmented reasoning and safeguards — [arXiv 2604.13940 via search](https://arxiv.org/pdf/2604.13940). Secondary coverage adds olmOCR preprocessing and parallel review modules, one of which runs evaluations in a Python code sandbox, on GPT-5 with API access sponsored by OpenAI. This is not confirmed in the primary abstract — [search summary of secondary blog](https://eu.36kr.com/en/p/3773078234268168).
- Results:
  - 5,834 survey responses from authors, PC, SPC and ACs.
  - AI reviews scored higher than human reviews on 6 of 9 quality criteria, and were preferred on technical accuracy and research suggestions. Authors preferred them more strongly than reviewers did.
  - Reported weaknesses: errors when reading equations and tables, poor ranking of which issues matter, and excessive length. Self-selection bias is acknowledged.
  - There was also an evaluation on a "SPECS" benchmark — [arXiv 2604.13940 via search](https://arxiv.org/pdf/2604.13940).
  - A dataset release was slated for August 2026 — [36Kr](https://eu.36kr.com/en/p/3773078234268168).

**Google Paper Assistant Tool (PAT): STOC 2026, then ICML 2026 and NeurIPS 2026.** Evidence: [VR], [PP].
- Links: [NeurIPS blog](https://blog.neurips.cc/?p=1509); [arXiv 2606.28277, "Towards Automating Scientific Review with Google's Paper Assistant Tool"](https://arxiv.org/pdf/2606.28277).
- How it works: an experimental pre-submission feedback tool built on a Gemini reasoning pipeline. It looks at experimental rigor, methodological soundness, English clarity and technical correctness. Reviewers, ACs and PCs cannot see the feedback. A later version added components from Google's "ScholarPeer" system, which the blog says improved fact-checking, reduced hallucinations and strengthened comparison with related work — [NeurIPS blog](https://blog.neurips.cc/?p=1509).
- Results:
  - STOC pilot: 94% of participants found it helpful, and 85% said it improved clarity — [NeurIPS blog](https://blog.neurips.cc/?p=1509).
  - On a SPOT subset of 26 math/CS papers with 29 equation or proof errors: Gemini 3.1 Pro zero-shot recalled more than 50%, and PAT reached 89.7% detection accuracy. Part of the gain is credited to a new "logic-aware grader", so the comparison with SPOT's o3 numbers is not like-for-like — [arXiv 2606.28277 via search](https://arxiv.org/pdf/2606.28277).
- Terms: free for participating venues; closed.

**Agents4Science 2025 (Stanford, 22 Oct 2025).** Evidence: [PP].
- Links: [arXiv 2511.15534](https://arxiv.org/pdf/2511.15534); [Science News](https://www.sciencenews.org/article/science-conference-test-ai-agents).
- What happened: 315 submissions, of which 62 were desk-rejected. Three LLM reviewers scored the remaining 253, the top 79 also got a human expert review, and 48 were accepted — [arXiv 2511.15534 via search](https://arxiv.org/pdf/2511.15534). I did not retrieve the findings on reviewer quality.

#### 1.4 Commercial and hosted products (claims are mostly [SR] unless noted)

**Refine (refine.ink).** Co-founded by Ben Golub (Northwestern, economics and computer science) and Yann Calvó López. The only product clearly built for economics.
- What it checks: referee-style feedback that identifies "errors in math and empirical strategy, clarity problems, and consistency issues" — [Princeton BCF event page](https://bcf.princeton.edu/events/benjamin-golub-on-modern-ai-for-economics-research-an-overview-of-tools/).
- Output format: each comment has a verbatim quote, a detailed explanation, a confidence score and a `paragraph_index` anchor — [OpenAIReview REPORT.md, which used Refine's published examples as ground truth](https://raw.githubusercontent.com/ChicagoHAI/OpenAIReview/HEAD/benchmarks/REPORT.md). A chat function allows follow-up questions — [Toda 2026](https://arxiv.org/pdf/2606.05383).
- Architecture: not public.
- Price: $49.99 per review — [Wheeler blog, Apr 2026](https://andrewpwheeler.com/2026/04/21/the-race-to-the-bottom-with-ai-tools/). Toda paid about $50 per analysis — [arXiv 2606.05383](https://arxiv.org/pdf/2606.05383). Purchases are non-refundable — [Manusights, a competitor](https://manusights.com/blog/is-refine-worth-it).
- Adoption claims [2nd and SR]: Marginal Revolution reports, citing the FT, that several top-five economics journals are experimenting with Refine. Golub said it flags problems in at least a third of papers that had already passed top-journal referees — [Marginal Revolution, Mar 2026](https://marginalrevolution.com/marginalrevolution/2026/03/is-ai-currently-helping-economic-research.html). A company announcement relayed on a discussion site says the AEA and the Econometric Society use its "technical verification"; this is unverified — [SocietySpeaks](https://societyspeaks.io/discussions/10721/solve-for-the-refine-equilibrium?lang=pt).
- Anecdotal quality:
  - John Cochrane judged its comments on a par with the best he had received in his career, though not perfect — [Arnold Kling's Substack](https://arnoldkling.substack.com/p/john-cochrane-gets-ai-pilled).
  - A competitor's review calls it strong on math and proof depth for theory papers, with named endorsers (Fudenberg, Lederman, Tamuz). It says Refine does not advertise citation verification or figure parsing, and that equations embedded in images are ignored — [Manusights](https://manusights.com/blog/is-refine-worth-it).
- Independent test [PP]: in Toda's test on economic theory papers with known errors, Refine's first report was underwhelming, but its chat later admitted a proof was incomplete and produced a counterexample. ChatGPT Pro did best of all tools tested, and "no model located a true error without substantial human guidance" — [arXiv 2606.05383](https://arxiv.org/pdf/2606.05383); [Marginal Revolution, Jun 2026](https://marginalrevolution.com/marginalrevolution/2026/06/how-well-does-current-ai-find-errors-in-economics-papers.html).

**q.e.d. science (QED Science; Oded Rechavi, Tel Aviv University, and Niv Samuel Mastboim).**
- What it does: uses generative AI "to analyse the claims and supporting data presented in manuscripts and identify 'gaps' that warrant further work or revision of the claims", and suggests fixes. bioRxiv authors can send papers to it, AI review is optional, and bioRxiv plans integration — [bioRxiv news, 2025-11-04](https://connect.biorxiv.org/news/2025/11/04/qed_review_tool).
- How it works: breaks papers into concrete claims; reports take about 30 minutes; released October 2025; a grant-review tool followed — [The Scientist](https://www.the-scientist.com/q-e-d-an-ai-tool-for-smarter-manuscript-review-73759); [Institut Pasteur open-science blog](https://openscience.pasteur.fr/2026/02/16/robot-reviewers-what-role-might-ai-play-in-evaluating-our-research-articles/).
- Claims [SR]: in June 2026 it scored 57,455 bioRxiv preprints (May 2025–April 2026) and published "The 1%", a list of the top 574. The company says its rankings often align with expert opinion. One beta tester said the suggestions were not original. A comparison with EMBO/Review Commons human reviews was run, but I found no published result — [The Scientist](https://www.the-scientist.com/can-ai-tools-spot-great-science-before-reviewers-do-74677). Product launch press release: [GlobeNewswire via StreetInsider](https://www.streetinsider.com/Globe+Newswire/QED+Science+Launches+AI+Infrastructure+for+Scientific+Validation/26681995.html).
- Scope: life sciences.

**Reviewer3 (reviewer3.com; Natalie Khalil and TJ Reed; founded 2025, San Diego).**
- How it works: a multi-agent system that tests whether conclusions hold up, not whether the work is novel. Agents rerun statistics, reproduce findings and validate code in a sandbox, then flag logical gaps or "fatal flaws". It cross-checks citations against five reference databases and includes AI-text detection — [The Scientist](https://www.the-scientist.com/reviewer3-an-ai-based-system-to-streamline-peer-review-74934); [PremierAlts](https://www.premieralts.com/companies/reviewer3).
- Independent evaluation: it was one of the systems in "Benchmarking Agentic Review Systems" (Q3), but I could not retrieve its per-system scores — [arXiv 2606.19749](https://arxiv.org/pdf/2606.19749).
- A competitor calls it "first-pass triage" — [Manusights](https://manusights.com/blog/reviewer3-review-2026).

**YesNoError (Matt Schlicht).**
- How it works: agents built on OpenAI o1 that audit papers and post flagged errors on its website and on X. A crypto token, $YNE, launched on December 20 (2024) and reportedly reached about $60M market cap. Holders can spend $YNE to prioritize review of a paper — [TechFlow](https://www.techflowpost.com/en-US/article/22690); [Odaily](https://www.odaily.news/post/5200893).
- Scale (conflicting): 2,219 papers reviewed per [TechFlow](https://www.techflowpost.com/en-US/article/22690); about 37,000 papers in two months per [GeekNews, Mar 2025](https://news.hada.io/topic?id=19634).
- Accuracy: most flagged papers had not been checked by experts, and I found no published accuracy — [GeekNews](https://news.hada.io/topic?id=19634); Nature news via [heise](https://heise.de/-10321469).

**IsItCredible.** Sold per use, with reports from $5. It is built on the open-source "Reviewer 2" pipeline and uses adversarial "Red Team" agents that hunt for flaws and "Blue Team" agents that check them — [Wheeler blog](https://andrewpwheeler.com/2026/04/21/the-race-to-the-bottom-with-ai-tools/).

#### 1.5 Open-source error finders and Claude Code skills

**Black Spatula Project (open community, started Dec 2024).** Evidence: [CODE], [2nd].
- Links: [GitHub README](https://raw.githubusercontent.com/The-Black-Spatula-Project/black-spatula-project/HEAD/README.md); [site README](https://raw.githubusercontent.com/The-Black-Spatula-Project/the-black-spatula-project.github.io/HEAD/README.md); [Nature news, Mar 2025](https://www.nature.com/articles/d41586-025-00648-5), which I could not open and read through [heise](https://heise.de/-10321469) and [getcoai](https://getcoai.com/news/oopsie-prevention-ai-tools-now-scan-scientific-papers-to-catch-critical-research-errors).
- How it works: volunteers test prompts and models (o1, GPT-4o, Gemini, Claude) on papers, including the WithdrarXiv dataset of withdrawn arXiv papers. Prompts and results are kept in shared Google Sheets, and domain experts volunteer to verify flagged errors. To run an analysis, you open a GitHub issue with the model in the title and the prompt and PDF in the body; the result appears as a comment — [README](https://raw.githubusercontent.com/The-Black-Spatula-Project/black-spatula-project/HEAD/README.md); [site README](https://raw.githubusercontent.com/The-Black-Spatula-Project/the-black-spatula-project.github.io/HEAD/README.md). The pipeline extracts text, tables and images, sends a complex prompt to a reasoning model, and sometimes analyzes a paper several times. Each paper costs from 15 cents to a few dollars — [getcoai summarizing Nature](https://getcoai.com/news/oopsie-prevention-ai-tools-now-scan-scientific-papers-to-catch-critical-research-errors).
- Accuracy: the system is wrong about an error "around 10% of the time" (Gulloso, quoted in Nature). About 500 papers have been analyzed. Expert verification is the bottleneck — [heise](https://heise.de/-10321469); [lennxa blog](https://lennxa.bearblog.dev/ai-checks-papers-for-errors/).
- Follow-up: an academic preprint inspired by the project tests reasoning models as checkers of critical errors on withdrawn arXiv papers — [arXiv 2505.23824](https://arxiv.org/pdf/2505.23824v1).
- License: MIT (copyright 2024 Anusheel Bhushan) — [LICENSE](https://raw.githubusercontent.com/The-Black-Spatula-Project/black-spatula-project/HEAD/LICENSE).

**OpenAIReview (Chicago Human+AI Lab, Chenhao Tan; 2026).** Evidence: [CODE], [PP].
- Links: [GitHub README](https://raw.githubusercontent.com/ChicagoHAI/OpenAIReview/HEAD/README.md); PyPI package `openaireview`; [UChicago news](https://cs.uchicago.edu/news/uchicago-researchers-build-a-tool-to-help-fix-peer-review/); [UChicago Data Science](https://datascience.uchicago.edu/insights/openaireview/).
- Inputs: PDF through Mistral OCR, then DeepSeek OCR, Marker, or pymupdf4llm as fallbacks; DOCX; LaTeX; Markdown; arXiv HTML. The README recommends `.tex`, Markdown or arXiv HTML for papers with math — [README](https://raw.githubusercontent.com/ChicagoHAI/OpenAIReview/HEAD/README.md).
- Methods: `zero_shot`; `local` (each paragraph deep-checked with a window of neighbouring paragraphs); and `progressive`, the default. Progressive reads about 8,000-character passages in order, keeps a running summary of up to about 2,000 tokens of notation, equations, theorems, assumptions and claims, and ends with one consolidation call. The default model is `anthropic/claude-opus-4-6` — [README](https://raw.githubusercontent.com/ChicagoHAI/OpenAIReview/HEAD/README.md); [REPORT.md](https://raw.githubusercontent.com/ChicagoHAI/OpenAIReview/HEAD/benchmarks/REPORT.md).
- Prompts:
  - Eight check categories: math and formula errors, notation, text versus formal definitions, numerical inconsistencies, insufficient justification, questionable claims, misleading ambiguity, and underspecified methods.
  - Leniency rules for introductions, forward references and informal paraphrase; a "do not flag" list; and an OCR caveat.
  - A three-tier severity rubric.
  - JSON output with fields `title`, `quote` (exact verbatim, preserving LaTeX), `explanation`, `type`, `severity` and `suggested_fix`. The suggested fix must be concrete, never "clarify this" — [prompts.py](https://raw.githubusercontent.com/ChicagoHAI/OpenAIReview/HEAD/src/reviewer/prompts.py).
- Bundled Claude Code skill `/openaireview`:
  - Pass A writes a structured summary of the paper.
  - Pass B launches 7–10 parallel subagents: one per section, plus 3–5 cross-cutting checks such as "Do abstract/introduction claims match evidence?", "Do numerical claims agree across sections?" and "Does the paper hold itself to the same standards it applies to others?".
  - Consolidation merges duplicates by root cause, removes false positives and verifies quotes.
  - Calibration rule: usually 3–7 major issues and 15–30 comments in total — [SKILL.md](https://raw.githubusercontent.com/ChicagoHAI/OpenAIReview/HEAD/src/reviewer/skill/SKILL.md); [criteria.md](https://raw.githubusercontent.com/ChicagoHAI/OpenAIReview/HEAD/src/reviewer/skill/references/criteria.md).
- Accuracy: see Q3. Recall against Refine's comments, then 83.0% pairwise accuracy and 71.6% injected-error recall in its own group's benchmark.
- License: MIT (2026) — [LICENSE](https://raw.githubusercontent.com/ChicagoHAI/OpenAIReview/HEAD/LICENSE).

**coarse (PyPI `coarse-ink`; GitHub `isitcredible/coarse`).** Evidence: [2nd], [CODE] via its competitor's adapter.
- What it is: a "free, open-source AI academic paper reviewer" where users bring their own API key. Version 1.9.6, about 610 downloads a month — [PyPI Stats](https://pypistats.org/packages/coarse-ink); [Wheeler blog](https://andrewpwheeler.com/2026/04/21/the-race-to-the-bottom-with-ai-tools/).
- Pipeline: extraction quality check → domain calibration → literature search → per-section agents → editorial filtering → quote verification — [OpenAIReview coarse report](https://raw.githubusercontent.com/ChicagoHAI/OpenAIReview/HEAD/benchmarks/conference_study/reports/coarse.md).
- License: the GitHub README was not reachable (404 at HEAD), so the license is unverified.

**AI-research-feedback (Claes Bäckman; 2026): Claude Code skills for economics papers.** Evidence: [CODE]. These are the closest prior art to the team's skill.
- Links: [README](https://raw.githubusercontent.com/claesbackman/AI-research-feedback/HEAD/README.md).
- The skills:
  - `/review-paper`: an 8-agent referee report targeting a journal (AER, QJE, JPE, Econometrica, REStud, JF, JFE, RFS, JFQA, AEJ Macro, JME or RED). The 8 agents cover:
    1. spelling and style;
    2. internal consistency and cross-references, where numbers in the text are checked against table `.tex` files;
    3. unsupported claims and identification, where a "skeptical econometrician" flags causal language without causal identification and flags "unverified priority assertions" without judging them;
    4. math, equations and notation, including formulas for standard errors and confidence intervals;
    5. tables and figures, for example whether confidence intervals are shown on event-study plots;
    6. a referee assessment of identification, required analyses, literature, journal fit and recommendation;
    7. a contribution steelman;
    8. a contribution skeptic.
  - `/review-paper-light` (2 agents); `/review-paper-checks` (3 agents, mechanical errors only); `/review-pap` for pre-analysis plans, with AEA, EGAP and OSF registries as targets; `/review-grant`; `/review-paper-code` for paper–code alignment in Stata, R or Python; `/audit-analysis` — [README](https://raw.githubusercontent.com/claesbackman/AI-research-feedback/HEAD/README.md); [review-paper SKILL.md](https://raw.githubusercontent.com/claesbackman/AI-research-feedback/HEAD/Skills/review-paper/SKILL.md).
- Guardrails:
  - A "scope guard" prepended verbatim to every agent: review only the listed files; ignore old reviews and drafts, `%` comments and `\todo{}`.
  - "Do not report an issue you cannot quote" — [review-paper-checks SKILL.md](https://raw.githubusercontent.com/claesbackman/AI-research-feedback/HEAD/Skills/review-paper-checks/SKILL.md).
  - Literature comparisons only from the paper's own bibliography. Anything else is labeled `[UNVERIFIED — based on general knowledge; authors must confirm]`, and authors, titles and findings must never be invented — [review-paper SKILL.md](https://raw.githubusercontent.com/claesbackman/AI-research-feedback/HEAD/Skills/review-paper/SKILL.md).
  - `audit-analysis` runs in an isolated subagent. It tags findings CONFIRMED or SUSPECTED, drops findings with no anchor in the code and counts them, and reports where it found nothing — [README](https://raw.githubusercontent.com/claesbackman/AI-research-feedback/HEAD/README.md).
  - The review skills set `disable-model-invocation: true` and accept LaTeX only — [README](https://raw.githubusercontent.com/claesbackman/AI-research-feedback/HEAD/README.md).
- Accuracy: I found no evaluation.
- License: MIT (2026) — [LICENSE](https://raw.githubusercontent.com/claesbackman/AI-research-feedback/HEAD/LICENSE).

**academic-research-skills (ARS; Cheng-I Wu, Imbad0202).** Evidence: [CODE].
- Features: an "Academic Paper Reviewer" with 7 agents (a journal-fit reviewer, 3 dynamic reviewers and a devil's advocate), integrity gates, and an opt-in calibration mode that measures its false negative and false positive rates against a user-supplied gold set. A claim-audit pass (v3.8) checks cited sources against each claim. It ships a 25-item synthetic gold set with acceptance thresholds of FNR < 0.15 and FPR < 0.10, but "no live-judge calibration result is recorded yet" — [README](https://raw.githubusercontent.com/Imbad0202/academic-research-skills/HEAD/README.md).
- Popularity: about 6,400 stars — [36Kr](https://eu.36kr.com/en/p/3812800346742274).
- License: CC BY-NC 4.0 (non-commercial) — [LICENSE](https://raw.githubusercontent.com/Imbad0202/academic-research-skills/HEAD/LICENSE). This contradicts a third-party guide that calls it MIT — [tosea.ai](https://tosea.ai/blog/academic-research-skills-claude-code-suite-guide-2026).

**OpenJudge `paper-review` (agentscope-ai; added 2026-01-27).** Checks for math errors, scores quality and novelty from 1 to 6, and verifies BibTeX entries against Crossref and arXiv. It uses vision-capable models by default — [Claude marketplace listing](https://claudemarketplaces.com/skills/agentscope-ai/openjudge/paper-review); [README](https://raw.githubusercontent.com/agentscope-ai/OpenJudge/HEAD/README.md). License: Apache-2.0 — [LICENSE](https://raw.githubusercontent.com/agentscope-ai/OpenJudge/HEAD/LICENSE).

**Other skills found but not inspected:**
- `paper-audit` (bahayonghang/academic-writing-skills) — [listing](https://claudemarketplaces.com/skills/bahayonghang/academic-writing-skills/paper-audit)
- `academic-paper-review` (bytedance/deer-flow) — [listing](https://claudemarketplaces.com/skills/bytedance/deer-flow/academic-paper-review)
- `paper-review` (evoscientist/evoskills) — [listing](https://claudemarketplaces.com/skills/evoscientist/evoskills/paper-review)
- K-Dense claude-scientific-skills, which is MIT-licensed — [LICENSE](https://raw.githubusercontent.com/K-Dense-AI/claude-scientific-skills/HEAD/LICENSE.md)

### Inferences
- The field split in 2025–2026. Older systems (Liang, MARG, Sakana, OpenReviewer, CycleReviewer, DeepReviewer, Stanford) imitate a conference review and are validated by agreement on scores or decisions. Newer tools (Refine, OpenAIReview, coarse, Reviewer3, Black Spatula, PAT, Bäckman's checks) list specific errors anchored to quotes. The team's DESIGN.md belongs to the second group; the first group is useful mainly for REV-04 simulated reviewers.
- Bäckman's MIT skills already do in Claude Code much of what DESIGN.md proposes for economics: COH-02 abstract fidelity, NUM-01 text against table `.tex` files, LOG-03 causal language, FACT-06 "unverified priority assertions", CIT-01 cite and `.bib` matching, FMT-05 cross-references, MTH-07 pre-analysis plans, and paper–code alignment. Forking or borrowing their agent prompts, with attribution, could save weeks. They do not do external lookups, deterministic statistics scripts, PDF or Word input, JSON findings, or a refutation pass, which are DESIGN.md's differentiators.
- Refine is the reference commercial product for economics. Its comment format (verbatim quote, explanation, confidence, paragraph anchor) is nearly the same as DESIGN.md's finding format, which suggests that format suits economists.

### Gaps
- Could not open vendor pages, so these remain unknown:
  - Refine's architecture, model and data-retention terms.
  - Reviewer3's and q.e.d.'s pricing.
  - YesNoError's current (2026) status.
  - paperreview.ai's pipeline steps and launch date (I believe November 2025, but did not verify).
- I could not confirm that Liang et al. was later published in NEJM AI (2024), or whether MARG appeared at a peer-reviewed venue.
- DeepReview's later stages beyond novelty verification were not verified. I recall a "reliability verification" stage but could not confirm it.
- No information on Google ScholarPeer beyond the NeurIPS blog mention; my search for it returned unrelated results.
- The exact attribution of some q.e.d. details between The Scientist and the Institut Pasteur blog was merged by the search tool and not verified.

## Q2. Design dimensions of each system: single prompt or multi-agent, chunking, retrieval, rubric, output, evaluation

### Takeaway
Most systems that find real errors use several passes over parts of the paper: section or passage agents, a running summary, or chunk-level deep checks, followed by consolidation. Single-prompt whole-paper review produces generic comments and finds few specific errors. Retrieval of related work appears only in a minority (Stanford, DeepReviewer, PAT with ScholarPeer, coarse), and is mostly arXiv-centric. Evaluation methods vary so much (overlap with humans, score correlation, user surveys, seeded-error recall, LLM-judged win rates) that published numbers cannot be compared across systems.

### Cited Findings

| System | Agents | Chunking or context | Related-work retrieval | Rubric or form | Output | How evaluated | Source |
|---|---|---|---|---|---|---|---|
| Liang et al. 2023 | Single GPT-4 call | Truncated to 6,500 tokens: abstract, captions, main text | No | 4-part outline: significance, accept reasons, reject reasons, suggestions | Free-text outline | Overlap with human reviews; survey of 308 users | [main.py](https://raw.githubusercontent.com/Weixin-Liang/LLM-scientific-feedback/HEAD/main.py); [README](https://raw.githubusercontent.com/Weixin-Liang/LLM-scientific-feedback/HEAD/README.md) |
| ReviewerGPT | Single prompt per task | Short papers | No | Task-specific: errors, checklist, pairs | Answers | 13 seeded errors; 119 checklist pairs; 10 pairs | [arXiv](https://arxiv.org/pdf/2306.00622) |
| MARG-S | Leader, chunk workers and 3 experts; refine-or-null pass | 4,096-token chunks | No | Experiments and proofs; novelty and impact; clarity and reproducibility | JSON list of comments | User study (9 people); alignment with ARIES data | [review_prompts.json](https://raw.githubusercontent.com/allenai/marg-reviewer/HEAD/review_worker/review_prompts.json); [arXiv](https://arxiv.org/pdf/2401.04259) |
| Sakana reviewer | Single model, plus reflection, ensemble and AC meta-review | Whole text from pymupdf4llm | No | NeurIPS form | THOUGHT and JSON scores, Accept or Reject | Decisions on 500 ICLR 2022 papers | [perform_review.py](https://raw.githubusercontent.com/SakanaAI/AI-Scientist/HEAD/ai_scientist/perform_review.py) |
| OpenReviewer | Fine-tuned 8B, single pass | Full paper, 128k context, Marker Markdown | No | ICLR 2025 template | Review with ratings | 400 papers, rating distribution | [README](https://raw.githubusercontent.com/maxidl/openreviewer/HEAD/README.md) |
| CycleReviewer | Fine-tuned model | Not retrieved | No | Conference scores | Review and scores | Score MAE; decision accuracy | [slides](https://iclr.cc/media/iclr-2025/Slides/32074.pdf) |
| DeepReviewer-14B | Fine-tuned, staged reasoning | Not retrieved | Yes: literature review in novelty verification | Multi-dimensional | Review and ratings | MSE, Spearman, LLM-judged win rates | [arXiv](https://arxiv.org/pdf/2503.08569) |
| Stanford Agentic Reviewer | Agentic | Not retrieved | Yes: arXiv | ICLR-style; 1–10 score trained on ICLR 2025 | Review and score | Spearman with humans | [tech overview](https://paperreview.ai/tech-overview) |
| ReviewerToo | gpt-oss-120b framework | Not retrieved | Not retrieved | ICLR | Review and decision | 1,963 ICLR 2025 decisions | [arXiv](https://arxiv.org/pdf/2510.08867) |
| ProReviewer | Agent with a structured review log, RL-trained 8B | Investigates parts on demand | Not retrieved | 5 quality dimensions | Review | Quality dimensions; human win rates | [arXiv](https://arxiv.org/pdf/2606.13349) |
| AgentReview | Reviewers, authors and AC; 5 phases | Not applicable | No | ICLR-like | Reviews, rebuttals, meta-reviews, decisions | Variation in decisions | [README](https://raw.githubusercontent.com/Ahren09/AgentReview/HEAD/README.md) |
| NeurIPS 2024 checklist assistant | One call per checklist question | Paper capped at about 15,000 words | No | NeurIPS checklist guidelines | Itemized feedback and score per question | Author surveys | [assistant.py](https://raw.githubusercontent.com/ihsaan-ullah/neurips-checklist-assistant/HEAD/SampleCode/assistant.py) |
| ICLR 2025 feedback agent | 2 actors → aggregator → critic → formatter, plus 4 LLM tests | Full paper and the review | No | Vague, misreading, unprofessional | Feedback items quoting the review | Randomized trial | [feedback_agent.py](https://raw.githubusercontent.com/zou-group/review_feedback_agent/HEAD/review_feedback_agent/agents/feedback_agent.py) |
| AAAI-26 pilot | Multi-stage, parallel modules, code sandbox (secondary report) | OCR (olmOCR, secondary report) | Not retrieved | Not retrieved | Labeled review, no scores | 5,834-response survey; SPECS benchmark | [arXiv](https://arxiv.org/pdf/2604.13940) |
| Google PAT | Gemini reasoning pipeline, plus ScholarPeer components | Not retrieved | Yes: related-work comparison, fact-checking | Rigor, soundness, clarity, correctness | Private feedback to authors | Surveys; SPOT subset | [NeurIPS blog](https://blog.neurips.cc/?p=1509); [arXiv](https://arxiv.org/pdf/2606.28277) |
| OpenAIReview (progressive) | Sequential passes, consolidation; skill uses 7–10 subagents | About 8,000-char passages and a 2,000-token running summary | None in the reviewed code | 8–10 error categories, 3 severity tiers | JSON with quote, explanation, severity, fix | Recall of Refine comments; seeded errors; accepted vs rejected | [REPORT.md](https://raw.githubusercontent.com/ChicagoHAI/OpenAIReview/HEAD/benchmarks/REPORT.md); [SKILL.md](https://raw.githubusercontent.com/ChicagoHAI/OpenAIReview/HEAD/src/reviewer/skill/SKILL.md) |
| coarse | Multi-stage, per-section agents | Per section | Yes: literature-search stage | Domain calibration | Comments with verified quotes | Third-party benchmark | [coarse report](https://raw.githubusercontent.com/ChicagoHAI/OpenAIReview/HEAD/benchmarks/conference_study/reports/coarse.md) |
| Bäckman `/review-paper` | 8 parallel Claude Code subagents and consolidation | Full LaTeX include-graph and table `.tex` files | No: limited to the paper's own bibliography | Economics journal targets; identification | Markdown report with [CRITICAL]/[MAJOR]/[MINOR] tags and quotes | None found | [SKILL.md](https://raw.githubusercontent.com/claesbackman/AI-research-feedback/HEAD/Skills/review-paper/SKILL.md) |
| Refine | Closed | Paragraph-indexed | Not stated | Math, empirical strategy, clarity, consistency | Quote, explanation, confidence, paragraph index; chat | Anecdotes; Toda | [REPORT.md](https://raw.githubusercontent.com/ChicagoHAI/OpenAIReview/HEAD/benchmarks/REPORT.md); [Princeton BCF](https://bcf.princeton.edu/events/benjamin-golub-on-modern-ai-for-economics-research-an-overview-of-tools/) |
| q.e.d. | Closed; breaks paper into claims | Not stated | Not stated | Claim–evidence gaps | Gaps, fixes and a score | Self-reported | [bioRxiv](https://connect.biorxiv.org/news/2025/11/04/qed_review_tool) |
| Reviewer3 | Closed, multi-agent | Not stated | Citation databases (5) | Do conclusions hold | Flags "fatal flaws" | Third-party benchmark | [The Scientist](https://www.the-scientist.com/reviewer3-an-ai-based-system-to-streamline-peer-review-74934) |
| Black Spatula | Single prompts to reasoning models, sometimes repeated | Extracted text, tables, images | No | Error-type prompts | Issue comments | Expert volunteers | [getcoai](https://getcoai.com/news/oopsie-prevention-ai-tools-now-scan-scientific-papers-to-catch-critical-research-errors) |
| SPOT harness | Several LLMs | Text chunks plus figures and tables as images | No | Find errors | Location and description | Matched to 91 annotated errors | [SPOT README](https://raw.githubusercontent.com/guijinSON/SPOT/HEAD/README.md) |

OpenAIReview's own comparison measured how much these choices matter. Zero-shot whole-paper review found 23 comments with 0% recall of Refine's issues, as judged by an LLM. Paragraph-level deep checks reached 15.4%, and progressive passes with a running summary reached 25.0%, or 44.2% before consolidation — [REPORT.md](https://raw.githubusercontent.com/ChicagoHAI/OpenAIReview/HEAD/benchmarks/REPORT.md).

### Inferences
- DESIGN.md's "parallel subagents, one per dimension" is like MARG-S and Bäckman. OpenAIReview's data suggests that per-dimension agents should still work passage by passage on long papers, with a shared summary of definitions and notation, rather than one pass over the whole paper. Otherwise recall of specific errors falls sharply.
- DESIGN.md's paper map is a richer version of OpenAIReview's running summary, holding sections, numbers, symbols and defined terms. Passing the relevant slice of the map to each reading agent is the same idea, and is likely to help LOG-07 and COH-06.
- For economics, related-work retrieval through arXiv alone, as the Stanford reviewer does, is likely to miss much of the literature, which lives on NBER, SSRN, RePEc and journal sites. DESIGN.md's lookup list (Crossref, OpenAlex, Semantic Scholar, arXiv) could add RePEc/IDEAS and SSRN search for CIT-09 and FACT-06.

### Gaps
- Chunking details for the AAAI-26, PAT, Refine, q.e.d., Reviewer3 and Stanford systems are not public or could not be retrieved.

## Q3. Accuracy evidence: error-detection benchmarks, false positives, agreement with humans, failure modes

### Takeaway
On real, published errors, LLMs find a minority and raise many false alarms. On SPOT, the best model (o3) had 21.1% recall and 6.1% precision. On FLAWS the best was 39.1% at k=10, and PRISMM-Bench scores ran 27.8–53.9%. With tighter scope (objective errors only), verification and generous grading, figures rise: 83.2% precision and 60% recall for GPT-5 on seeded errors, and 89.7% for PAT on math errors with a lenient grader. Agreement with human reviewers on scores and decisions is about at the level humans reach with each other, but that says little about correctness. The documented failure modes are generic comments, positivity bias, a "hivemind" of near-identical reviews, gaming by restyling, prompt injection, bias by author identity, errors reading equations and tables, poor reproducibility across runs, and missed deep math errors.

### Cited Findings

#### Error-detection benchmarks

| Benchmark or study | Data | Best reported result | Caveats | Source |
|---|---|---|---|---|
| SPOT (May 2025) [PP] | 83 published papers, 91 errors serious enough for errata or retraction, from PubPeer and withdrawn arXiv papers | o3: precision 6.1% (±1.3), recall 21.1% (±4.4) over 8 trials; all other models near zero | A true positive needs a matching location and LLM-confirmed equivalence; annotations treated as exhaustive; models "rarely rediscover the same errors" across runs | [arXiv 2505.11855](https://arxiv.org/pdf/2505.11855); [SPOT README](https://raw.githubusercontent.com/guijinSON/SPOT/HEAD/README.md) |
| FLAWS (Nov 2025, CMU) [PP] | 713 paper–error pairs; claim-invalidating errors inserted by an LLM | GPT-5: 39.1% identification at k=10 | Synthetic errors | [arXiv 2511.21843](https://arxiv.org/pdf/2511.21843) |
| PRISMM-Bench (ICLR 2026) [PR] | Inconsistencies across text, figures, tables and equations that real reviewers flagged; v1 262 from 242 papers, later 384 from 353 | 21 multimodal models scored 26.1–54.2% (v1) and 27.8–53.9% (latest) | Multiple-choice and matching tasks | [arXiv 2510.16505](https://arxiv.org/pdf/2510.16505); [ICLR 2026](https://iclr.cc/virtual/2026/poster/10007547) |
| "To Err Is Human" (Dec 2025; Together AI, Stanford, others) [PP] | GPT-5 "Paper Correctness Checker"; objective errors only; 60-paper validation set; 90 injected errors | Precision 83.2% (263 of 316 flags confirmed by experts); recall 60.0% on injected errors (math 66.7%, cross-reference 53.8%, text 55.9%) | Mistakes per paper rose from 3.8 (NeurIPS 2021) to 5.9 (NeurIPS 2025) and from 4.1 (ICLR 2018) to 5.2 (ICLR 2025) | [arXiv 2512.05925](https://arxiv.org/pdf/2512.05925) |
| PAT on a SPOT subset (Jun 2026) [PP] | 26 papers with 29 equation or proof errors | Gemini 3.1 Pro zero-shot over 50% recall; PAT 89.7% | Uses a new "logic-aware grader"; not like-for-like with SPOT | [arXiv 2606.28277](https://arxiv.org/pdf/2606.28277) |
| Benchmarking Agentic Review Systems (Nguyen, Hao, Elazar, Tan; Jun 2026) [PP; listed at NeurIPS 2026] | OpenAIReview, coarse, Reviewer3 and a zero-shot baseline on 6 LLMs; 30 high- and 30 low-quality papers for each of 4 quality proxies; perturbation benchmark | Pairwise accuracy (low-quality paper gets more comments) 83.0% for OpenAIReview with GPT-5.5; 89.3% comment precision by LLM judges validated by humans; 71.6% of injected errors caught | Co-author Chenhao Tan leads the lab that built OpenAIReview; precision is judged by LLMs | [arXiv 2606.19749](https://arxiv.org/pdf/2606.19749); [NeurIPS 2026 listing](https://neurips.cc/virtual/2026/166246); [UChicago news](https://cs.uchicago.edu/news/uchicago-researchers-build-a-tool-to-help-fix-peer-review/) |
| OpenAIReview against Refine's comments (Mar 2026) [CODE] | 4 papers, 52 Refine comments as ground truth | Progressive: 25.0% recall and 19.1% precision by LLM judge; progressive before consolidation: 44.2% recall, 9.3% precision, 82.7% location recall; zero-shot 0%; cost about $4 per paper with Claude Opus 4.5 | Refine's comments are not a complete ground truth; one information-theory paper stayed at 16% | [REPORT.md](https://raw.githubusercontent.com/ChicagoHAI/OpenAIReview/HEAD/benchmarks/REPORT.md) |
| ReviewerGPT (2023) [PP] | 13 short papers with one inserted error each | 7 of 13 found | Tiny sample | [arXiv 2306.00622](https://arxiv.org/pdf/2306.00622) |
| REPRO-Bench (ACL 2025) [PR] | 112 social-science papers with public reproduction reports | Best existing agent 21.4%; REPRO-Agent 71% higher; Claude 4.5 Opus and GPT-5.2 still poor (author blog) | Tests reproducibility assessment, not reading | [arXiv 2507.18901](https://arxiv.org/pdf/2507.18901); [author blog](https://ddkang.substack.com/p/claude-45-opus-solves-core-bench) |

#### False positives and precision in the field
- Black Spatula: wrong about a flagged error about 10% of the time, according to project lead Gulloso as quoted in Nature — [heise](https://heise.de/-10321469).
- SPOT: 6.1% precision for the best model — [arXiv 2505.11855](https://arxiv.org/pdf/2505.11855).
- "To Err Is Human": 83.2% of flags confirmed by human experts — [arXiv 2512.05925](https://arxiv.org/pdf/2512.05925).
- NeurIPS checklist assistant: inaccuracy was the most common complaint (20 of 52) — [arXiv 2411.03417](https://arxiv.org/html/2411.03417v2).
- OpenAIReview: precision 9.3% before consolidation and 19.1% after — [REPORT.md](https://raw.githubusercontent.com/ChicagoHAI/OpenAIReview/HEAD/benchmarks/REPORT.md).
- The precision numbers conflict because the definitions differ: matching to an exhaustive annotation set (SPOT) versus expert confirmation of flags (To Err Is Human) — [36Kr discussion](https://eu.36kr.com/en/p/3931963588836487).

#### Agreement with human reviewers
- Liang: 30.85% and 39.23% overlap with human comments, against 28.58% and 35.25% between humans — [README](https://raw.githubusercontent.com/Weixin-Liang/LLM-scientific-feedback/HEAD/README.md).
- Stanford reviewer: Spearman 0.42 with a human, against 0.41 between humans [SR] — [tech overview](https://paperreview.ai/tech-overview).
- ReviewerToo: 81.8% decision accuracy against 83.9% for humans — [arXiv 2510.08867](https://arxiv.org/pdf/2510.08867).
- Sakana: about 70% accuracy against 73% for humans; balanced accuracy 69% in the Nature version — [arXiv 2408.06292](https://arxiv.org/pdf/2408.06292); [Sakana](https://sakana.ai/ai-scientist-nature/).
- CycleReviewer: 26.89% lower MAE than individual humans — [arXiv 2411.00816](https://arxiv.org/pdf/2411.00816).
- Counter-evidence from an ICML 2026 oral position paper using ICLR 2026 data: human scores predicted acceptance better than AI scores (AUC 0.822 vs 0.710) — [ICML 2026](https://icml.cc/virtual/2026/poster/67247); [AI Weekly](https://aiweekly.co/alerts/baumann-et-al-ai-peer-reviewers-hivemind-and-get-gamed).

#### Failure modes
- **Generic comments:**
  - A GPT-4 baseline produced 60% generic comments (MARG study) — [arXiv 2401.04259](https://arxiv.org/pdf/2401.04259).
  - Liang: comments tend toward "add experiments on more datasets" and give shallow critique of methods — [README](https://raw.githubusercontent.com/Weixin-Liang/LLM-scientific-feedback/HEAD/README.md).
  - A related observation: in OpenAIReview's study, coarse produced the same number of comments on accepted and rejected ICLR papers (13.3 vs 13.0 on average), while OpenAIReview produced 14–19% more on rejected papers — [coarse report](https://raw.githubusercontent.com/ChicagoHAI/OpenAIReview/HEAD/benchmarks/conference_study/reports/coarse.md).
- **Positivity and sycophancy:**
  - General LLMs skew toward overly positive recommendations — [OpenReviewer](https://arxiv.org/pdf/2412.11948v1).
  - LLMs give more positive feedback than human reviewers, their scores cluster around 5–8, and they do not mirror low human ratings — [arXiv 2509.09912](https://arxiv.org/pdf/2509.09912).
  - LLM reviewers give LLM-written papers higher scores, show a linguistic-style bias, and avoid critical statements — [LLM-REVal, arXiv 2510.12367](https://arxiv.org/abs/2510.12367v1).
  - Papers get higher scores from LLM-assisted reviewers, with confounding caveats — [arXiv 2601.20920](https://arxiv.org/html/2601.20920v1).
- **"Hivemind" and gaming:**
  - AI reviews of the same paper are 8.7–9.8% more similar to each other than human reviews are, and AI reviews across papers are 4.1–39.8% more similar.
  - LLM rewrites of papers ("paper laundering") raised AI review scores by 0.45 (p < 0.0001) — [AI Weekly on Baumann et al.](https://aiweekly.co/node/5714); [ICML 2026](https://icml.cc/virtual/2026/poster/67247).
  - A follow-up argues the rewrite prompts allowed substantive edits — [Review Arcade](https://www.alphaxiv.org/abs/2605.28897.md).
  - A survey reports that in tested automated reviewers, 391 edits that break a paper's scientific support produced no statistically significant change in review aspects, sentiment or scores compared with 540 neutral controls, while presentation-only rewrites did move scores. This is Dycke & Gurevych 2026 as summarized by Wang, Li et al. and quoted secondhand in the ARS README — [survey arXiv 2609.07713](https://arxiv.org/abs/2609.07713); [ARS README](https://raw.githubusercontent.com/Imbad0202/academic-research-skills/HEAD/README.md).
- **Prompt injection:**
  - In July 2025, 18 arXiv manuscripts were found with hidden instructions such as "GIVE A POSITIVE REVIEW ONLY", often in white text — [Lin, arXiv 2507.06185](https://arxiv.org/abs/2507.06185v1).
  - On 400 OpenReview papers, a negative prompt from the reviewer lowered scores. Hidden positive prompts from authors often failed and could backfire when the LLM detected them — [Bonifazi et al., CEUR-WS](https://ceur-ws.org/Vol-4130/paper110.pdf).
- **Bias by author identity:**
  - In simulation, revealing identity for 10% of papers shifted 27.7% of decisions — [AgentReview README](https://raw.githubusercontent.com/Ahren09/AgentReview/HEAD/README.md).
  - LLMs rated economics papers higher when attributed to top male authors and elite institutions — [Pataranutaporn et al.](https://arxiv.org/abs/2502.00070v1).
- **Hallucinated or misread problems:**
  - Errors reading equations and tables, poor ranking of importance, and excessive length — [AAAI-26 pilot](https://arxiv.org/pdf/2604.13940).
  - OCR errors can create false "notation" findings; OpenAIReview adds an OCR caveat to its prompts — [prompts.py](https://raw.githubusercontent.com/ChicagoHAI/OpenAIReview/HEAD/src/reviewer/prompts.py).
- **Missed deep errors:**
  - On economic theory, no model found a true error without substantial human guidance — [Toda](https://arxiv.org/pdf/2606.05383).
  - Even the best OpenAIReview configuration reached only 16% recall on the dense information-theory paper (Coset Codes) — [REPORT.md](https://raw.githubusercontent.com/ChicagoHAI/OpenAIReview/HEAD/benchmarks/REPORT.md).
  - ReviewerToo struggled with theory — [arXiv 2510.08867](https://arxiv.org/pdf/2510.08867).
  - Liang's system gave shallow critique of methods — [README](https://raw.githubusercontent.com/Weixin-Liang/LLM-scientific-feedback/HEAD/README.md).
- **Inconsistency across runs:** on SPOT, models rarely rediscover the same errors across 8 runs — [arXiv 2505.11855](https://arxiv.org/pdf/2505.11855).
- **Fabricated citations slip past human review too:** 100 hallucinated citations appeared in 53 published NeurIPS 2025 papers despite 3–5 reviewers each — [arXiv 2602.05930](https://arxiv.org/pdf/2602.05930).

### Inferences
- The team should expect low recall on deep errors in proofs and statistics from the READ checks, and should report coverage honestly, as DESIGN.md section 8.4 already plans. LOG-07 claims should default to "needs human judgment".
- The deterministic SCRIPT checks in DESIGN.md (statcheck-style, GRIM, arithmetic, cross-references) target exactly the error class LLMs read badly: tables and equations, per the AAAI pilot. That justifies keeping them separate from the LLM agents.
- Because published precision runs from 6% to 89% depending on definitions, the only meaningful accuracy number for the skill will be one measured on its own seeded-error set of behavioral economics drafts. DESIGN.md open question 6 asks for drafts with known problems. A perturbation pipeline (OpenAIReview, FLAWS) could generate controlled errors in clean drafts.
- REV-04 simulated reviewers are exposed to the positivity, hivemind, identity-bias and restyling-gaming failure modes. The persona output should stay labeled "Suggestion" and never become a score, which DESIGN.md already does.

### Gaps
- Per-system results for coarse and Reviewer3 in "Benchmarking Agentic Review Systems", and the SPECS benchmark results in the AAAI report, could not be retrieved.
- No benchmark built from economics or behavioral economics papers was found, except Toda's four theory papers, REPRO-Bench (social science, reproducibility), and the one economic theory paper in OpenAIReview's set.
- I found no study that directly measures how often LLM reviews invent problems in tables or regressions in empirical economics papers.

## Q4. Which prompts, rubrics, review forms or code are open and reusable, and under what licenses?

### Takeaway
The most reusable, permissively licensed assets are:
- OpenAIReview's prompts and Claude Code skill (MIT);
- Bäckman's economics review skills (MIT);
- the ICLR feedback agent's critic and reliability-test pattern (MIT);
- the NeurIPS checklist prompt (MIT);
- MARG's multi-agent and refine prompts (Apache-2.0);
- AgentReview's persona framework (Apache-2.0);
- Liang et al.'s prompt (CC BY 4.0).

Avoid copying from the Sakana AI Scientist (a license based on the Responsible AI license, with a disclosure clause that must be passed on), CycleResearcher and DeepReviewer (non-commercial, registration required), and academic-research-skills (CC BY-NC 4.0).

### Cited Findings

| Asset | Reusable part | License | Source |
|---|---|---|---|
| OpenAIReview | 8-category check criteria, leniency rules, do-not-flag list, OCR caveat, 3-tier severity rubric, JSON finding schema with verbatim quote and concrete fix, consolidation prompt, running-summary prompt, Claude Code skill (Pass A summary, section and cross-cutting subagents, merge by root cause, quote verification, calibration of 3–7 majors), perturbation benchmark | MIT | [prompts.py](https://raw.githubusercontent.com/ChicagoHAI/OpenAIReview/HEAD/src/reviewer/prompts.py); [SKILL.md](https://raw.githubusercontent.com/ChicagoHAI/OpenAIReview/HEAD/src/reviewer/skill/SKILL.md); [LICENSE](https://raw.githubusercontent.com/ChicagoHAI/OpenAIReview/HEAD/LICENSE) |
| Bäckman AI-research-feedback | 8 economics agent prompts (consistency against table `.tex`, causal-language "claim discipline", math and regression specification, tables and figures, referee, steelman, skeptic), scope guard, quote-anchoring rule, [UNVERIFIED] label convention, pre-analysis-plan review, paper–code audit (CONFIRMED vs SUSPECTED) | MIT | [README](https://raw.githubusercontent.com/claesbackman/AI-research-feedback/HEAD/README.md); [LICENSE](https://raw.githubusercontent.com/claesbackman/AI-research-feedback/HEAD/LICENSE) |
| ICLR 2025 Review Feedback Agent | Actor ×2 → aggregator → critic → formatter; four LLM "unit tests", including the verbatim-quote test | MIT | [reliability_tests.py](https://raw.githubusercontent.com/zou-group/review_feedback_agent/HEAD/review_feedback_agent/tests/reliability_tests.py); [LICENSE](https://raw.githubusercontent.com/zou-group/review_feedback_agent/HEAD/LICENSE) |
| NeurIPS 2024 checklist assistant | Per-question prompt (question, answer, justification, guidelines, paper → discrepancies and feedback), format checker, adversarial-attack notebooks | MIT | [SamplePrompt](https://raw.githubusercontent.com/ihsaan-ullah/neurips-checklist-assistant/HEAD/SamplePrompt/README.md); [LICENSE](https://raw.githubusercontent.com/ihsaan-ullah/neurips-checklist-assistant/HEAD/LICENSE) |
| MARG | Leader and worker protocol, 3 expert personas, refine-or-null comment prompt, alignment evaluation code | Apache-2.0 | [review_prompts.json](https://raw.githubusercontent.com/allenai/marg-reviewer/HEAD/review_worker/review_prompts.json); [README](https://raw.githubusercontent.com/allenai/marg-reviewer/HEAD/README.md) |
| AgentReview | Reviewer and AC persona traits; review, rebuttal and meta-review simulation | Apache-2.0 | [README](https://raw.githubusercontent.com/Ahren09/AgentReview/HEAD/README.md); [LICENSE](https://raw.githubusercontent.com/Ahren09/AgentReview/HEAD/LICENSE) |
| Liang et al. | 4-part feedback prompt, ScienceBeam pipeline | CC BY 4.0 | [main.py](https://raw.githubusercontent.com/Weixin-Liang/LLM-scientific-feedback/HEAD/main.py); [LICENSE](https://raw.githubusercontent.com/Weixin-Liang/LLM-scientific-feedback/HEAD/LICENSE) |
| OpenJudge `paper-review` | Math-error check, 1–6 scoring, BibTeX verification against Crossref and arXiv | Apache-2.0 | [README](https://raw.githubusercontent.com/agentscope-ai/OpenJudge/HEAD/README.md); [LICENSE](https://raw.githubusercontent.com/agentscope-ai/OpenJudge/HEAD/LICENSE) |
| Black Spatula | Issue-bot pipeline; prompt and result spreadsheets (the sheets' license is unstated) | MIT for the code | [README](https://raw.githubusercontent.com/The-Black-Spatula-Project/black-spatula-project/HEAD/README.md); [LICENSE](https://raw.githubusercontent.com/The-Black-Spatula-Project/black-spatula-project/HEAD/LICENSE) |
| SPOT | Annotation app, processing pipeline, LLM outputs on Hugging Face (`amphora/spot-results`) | License not checked | [SPOT README](https://raw.githubusercontent.com/guijinSON/SPOT/HEAD/README.md) |
| Sakana AI Scientist reviewer | NeurIPS form, THOUGHT and JSON template, reflection and ensemble code, negative-bias system prompt | AI Scientist Source Code License (Responsible-AI based); disclosure clause; restrictions must be passed on | [perform_review.py](https://raw.githubusercontent.com/SakanaAI/AI-Scientist/HEAD/ai_scientist/perform_review.py); [LICENSE](https://raw.githubusercontent.com/SakanaAI/AI-Scientist/HEAD/LICENSE) |
| CycleResearcher, CycleReviewer, DeepReviewer (WestlakeNLP "Researcher" repo) | Models and data | CycleResearcher License: non-commercial, registration, disclosure | [LICENSE.md](https://raw.githubusercontent.com/zhu-minjun/Researcher/HEAD/LICENSE.md) |
| academic-research-skills | 7-agent reviewer, devil's advocate, FNR/FPR calibration runner | CC BY-NC 4.0; a third-party guide wrongly says MIT | [LICENSE](https://raw.githubusercontent.com/Imbad0202/academic-research-skills/HEAD/LICENSE); [tosea.ai](https://tosea.ai/blog/academic-research-skills-claude-code-suite-guide-2026) |
| OpenReviewer | Training scripts; Llama-OpenReviewer-8B | No root LICENSE found; model license not verified | [README](https://raw.githubusercontent.com/maxidl/openreviewer/HEAD/README.md) |
| coarse | Full pipeline | "Open-source" per PyPI; license not verified | [PyPI Stats](https://pypistats.org/packages/coarse-ink) |
| ProReviewer-8B | Model | MIT per the model card | [Friendli](https://friendli.ai/models/UKPLab/ProReviewer-8B) |
| Closed: Refine, q.e.d., Reviewer3, YesNoError, IsItCredible, paperreview.ai, PAT | — | Commercial or free-hosted; no code | Q1 sources |

### Inferences
- The fastest legal path to working reading agents is to adapt Bäckman's economics agent prompts and OpenAIReview's criteria, leniency rules, JSON schema and consolidation rules under MIT, with attribution in the skill's README or NOTICE file. The ICLR agent's four reliability tests are a ready template for DESIGN.md guardrail 1 (quote verification) and for checks that a finding is actionable and not just praise.
- The NeurIPS checklist prompt maps directly onto MTH-06 and FMT-03: verify each answer and justification on the checklist against the paper. Swapping NeurIPS guidelines for an economics journal's data and code availability policy, or for a pre-registration checklist, is a small change.
- Copying Sakana's form into a shared GitHub skill would bring obligations from its Responsible-AI-based license. Writing a new economics persona form is cleaner.

### Gaps
- I did not check licenses for SPOT, coarse, or the OpenReviewer model card, nor the content of K-Dense's skills.

## Q5. What techniques reduce false findings, and how good is the evidence?

### Takeaway
The evidence favors three techniques:
- **Verbatim quote anchoring**, with mechanical verification and dropping unanchored findings.
- **A consolidation or critic pass.** It roughly doubles precision but costs recall.
- **Narrow, targeted prompts and deterministic tools** for numbers and code instead of holistic review.

Self-reflection helps a little, by about 2 points. Ensembles mainly reduce variance. Multi-agent debate did not beat a single strong pass in the one controlled economics trial. Retrieval-based grounding and red-team/blue-team setups are plausible but rest mostly on vendor claims. Agreement across repeated runs is a cheap confidence signal suggested by SPOT's finding that errors are rarely found again.

### Cited Findings
- **Quote anchoring and verification.**
  - The ICLR feedback agent sends nothing unless an LLM test confirms that every quoted review comment appears verbatim. Its trial produced 12,222 incorporated suggestions — [reliability_tests.py](https://raw.githubusercontent.com/zou-group/review_feedback_agent/HEAD/review_feedback_agent/tests/reliability_tests.py); [ICLR blog](https://blog.iclr.cc/2025/04/15/leveraging-llm-feedback-to-enhance-review-quality/).
  - OpenAIReview requires "exact verbatim" quotes and verifies them during consolidation — [prompts.py](https://raw.githubusercontent.com/ChicagoHAI/OpenAIReview/HEAD/src/reviewer/prompts.py); [SKILL.md](https://raw.githubusercontent.com/ChicagoHAI/OpenAIReview/HEAD/src/reviewer/skill/SKILL.md).
  - coarse ends with a quote-verification stage — [coarse report](https://raw.githubusercontent.com/ChicagoHAI/OpenAIReview/HEAD/benchmarks/conference_study/reports/coarse.md).
  - Bäckman's skills say "Do not report an issue you cannot quote", and `audit-analysis` drops unanchored findings and counts them — [review-paper-checks](https://raw.githubusercontent.com/claesbackman/AI-research-feedback/HEAD/Skills/review-paper-checks/SKILL.md); [README](https://raw.githubusercontent.com/claesbackman/AI-research-feedback/HEAD/README.md).
- **Consolidation or a critic pass, and the recall trade-off.**
  - OpenAIReview's consolidation cut comments from 247 to 68. Precision rose from 9.3% to 19.1%, while recall fell from 44.2% to 25.0% — [REPORT.md](https://raw.githubusercontent.com/ChicagoHAI/OpenAIReview/HEAD/benchmarks/REPORT.md).
  - MARG's refine-or-null pass and its specialists together cut generic comments from 60% to 29% — [arXiv 2401.04259](https://arxiv.org/pdf/2401.04259); [review_prompts.json](https://raw.githubusercontent.com/allenai/marg-reviewer/HEAD/review_worker/review_prompts.json).
  - The ICLR agent runs a dedicated FeedbackCritic after aggregation — [feedback_agent.py](https://raw.githubusercontent.com/zou-group/review_feedback_agent/HEAD/review_feedback_agent/agents/feedback_agent.py).
  - The OpenAIReview skill warns against over-merging: "For any singleton finding... read its full text before deciding to drop — these are the most likely to be unique insights" — [SKILL.md](https://raw.githubusercontent.com/ChicagoHAI/OpenAIReview/HEAD/src/reviewer/skill/SKILL.md).
- **Leniency and "do not flag" rules.** OpenAIReview tells checkers to be lenient with introductions, forward references and paraphrase, not to flag OCR misreads, and to "first try to understand the authors' intent". However, the same leniency in a single zero-shot pass gave 0% recall, so these rules can suppress too much — [prompts.py](https://raw.githubusercontent.com/ChicagoHAI/OpenAIReview/HEAD/src/reviewer/prompts.py); [REPORT.md](https://raw.githubusercontent.com/ChicagoHAI/OpenAIReview/HEAD/benchmarks/REPORT.md).
- **Targeted prompts instead of holistic review.** GPT-4 did better when prompted specifically to find errors — [FLAWS citing ReviewerGPT](https://arxiv.org/html/2511.21843v1). The checklist assistant asks one question per call — [assistant.py](https://raw.githubusercontent.com/ihsaan-ullah/neurips-checklist-assistant/HEAD/SampleCode/assistant.py).
- **Self-reflection and ensembles.**
  - Sakana: reflection added about 2% and one-shot prompting about 2%. Ensembling "does not appear to improve... substantially but can reduce variance" — [arXiv 2408.06292](https://arxiv.org/pdf/2408.06292). Later work found o4-mini with a 5-review ensemble and meta-review best — [arXiv 2606.15497](https://arxiv.org/pdf/2606.15497).
  - ReviewerGPT used a majority vote over 3 queries per checklist item — [arXiv 2306.00622](https://arxiv.org/pdf/2306.00622).
  - SPOT: models rarely rediscover the same errors across 8 runs — [arXiv 2505.11855](https://arxiv.org/pdf/2505.11855).
- **Multi-agent debate.**
  - In a pre-registered, identity-masked trial, 44 meta-analysis authors ranked a single frontier-model pass above two debate tools, by 0.66 and 0.57 rank points. One of the debate tools used about 30 times the tokens — [Havranek and Irsova](https://econpapers.repec.org/RePEc:arx:papers:2607.14713).
  - In AgentReview's simulation, social influence among agents cut the spread of ratings by 27.2% — [AgentReview README](https://raw.githubusercontent.com/Ahren09/AgentReview/HEAD/README.md).
- **Adversarial roles.** IsItCredible pairs "Red Team" flaw-hunters with "Blue Team" checkers [SR] — [Wheeler](https://andrewpwheeler.com/2026/04/21/the-race-to-the-bottom-with-ai-tools/). Bäckman pairs a contribution steelman with a skeptic — [SKILL.md](https://raw.githubusercontent.com/claesbackman/AI-research-feedback/HEAD/Skills/review-paper/SKILL.md). I found no quantitative evaluation of either.
- **Grounding through retrieval and tools.**
  - The Stanford reviewer grounds in arXiv [SR] — [tech overview](https://paperreview.ai/tech-overview).
  - PAT's ScholarPeer components "improved fact-checking, reduced hallucinations" [VR, tool-provider claim] — [NeurIPS blog](https://blog.neurips.cc/?p=1509).
  - Reviewer3 reruns statistics and validates code in a sandbox [SR] — [The Scientist](https://www.the-scientist.com/reviewer3-an-ai-based-system-to-streamline-peer-review-74934).
  - The AAAI pilot reportedly used a Python sandbox [2nd] — [36Kr](https://eu.36kr.com/en/p/3773078234268168).
- **A running context of definitions.** Adding a definitions prefix lifted recall on the economic theory paper from 0% to 50%. A progressive running summary beat paragraph-level checking, 25% against 15% — [REPORT.md](https://raw.githubusercontent.com/ChicagoHAI/OpenAIReview/HEAD/benchmarks/REPORT.md).
- **Countering positivity.** Sakana's default prompt says "If a paper is bad or you are unsure, give it bad scores and reject it" — [perform_review.py](https://raw.githubusercontent.com/SakanaAI/AI-Scientist/HEAD/ai_scientist/perform_review.py). A negative instruction from the reviewer reliably lowered LLM scores — [Bonifazi et al.](https://ceur-ws.org/Vol-4130/paper110.pdf).
- **Human verification.**
  - Black Spatula relies on volunteer experts — [README](https://raw.githubusercontent.com/The-Black-Spatula-Project/black-spatula-project/HEAD/README.md).
  - "To Err Is Human" measured precision by expert confirmation — [arXiv 2512.05925](https://arxiv.org/pdf/2512.05925).
  - Toda found that a competent human paired with a frontier model can beat current peer review, while the AI alone could not — [arXiv 2606.05383](https://arxiv.org/pdf/2606.05383).
- **Calibration against a gold set.** ARS sets FNR < 0.15 and FPR < 0.10 thresholds on a 25-item synthetic set, but has no live result yet — [ARS README](https://raw.githubusercontent.com/Imbad0202/academic-research-skills/HEAD/README.md).
- **Avoid an AI judge as the yardstick.** In the economics trial, Gemini as judge would have reversed the authors' ranking. Three AI judges almost always ranked the real referee report last, even though authors who recognized it ranked it first — [Havranek and Irsova](https://econpapers.repec.org/RePEc:arx:papers:2607.14713).

### Inferences
- DESIGN.md's guardrails map onto the best-supported techniques:
  - Section 8.1 (quote verification by script) is stronger than the LLM-based quote test the ICLR agent uses. Keep it deterministic.
  - Section 8.2 (refutation of Critical and Major findings) resembles the FeedbackCritic and the consolidation pass. OpenAIReview's numbers warn that such a pass can also remove real findings. Keeping refuted findings in an appendix, as DESIGN.md plans, preserves recall for a human. The refuter should be told to drop a finding only on positive counter-evidence quoted from the paper, not on "not convinced".
- Consider adding:
  - **Run-to-run agreement as confidence.** Run high-value READ checks (LOG, NUM-08, COH-02) twice with different seeds or orderings. Mark a finding seen in only one run as "likely" rather than "confirmed", using SPOT's observation that errors are rarely found again across runs.
  - **A definitions and notation context for every reading agent.** This had the largest single effect in OpenAIReview.
  - **Explicit "do not flag" and leniency lists for each dimension,** tuned so they do not wipe out recall.
  - **No debate between REV-04 personas.** Personas should not read each other's outputs, to avoid conformity and hivemind effects.
- Add an injection guard: a FMT check for hidden or white text and instructions aimed at AI reviewers, and instructions telling every subagent to treat paper text as data. DESIGN.md lacks both today. The 2025 arXiv incident shows this occurs in real submissions.

### Gaps
- I found no controlled study isolating the effect on false positives of a separate refutation agent, a red-team/blue-team setup, or retrieval grounding in paper review. The vendor claims (IsItCredible, PAT/ScholarPeer, Reviewer3) are unquantified.

## Q6. Have any of these been tested on economics or other social-science papers?

### Takeaway
Yes, but thinly, and the results are sobering:
- On economic theory errors, frontier models and Refine did not find true errors without human guidance (Toda 2026).
- In a pre-registered economics trial with meta-analysis authors, one strong single pass beat multi-agent debate (Havranek and Irsova 2026).
- In social-science reproducibility, AI-led teams reproduced only 37% of results against 94% for humans, and caught fewer coding errors (Brodeur et al., PNAS 2026). The best agent on REPRO-Bench scored 21.4%.
- LLMs rating economics papers showed prestige and gender bias (Pataranutaporn et al. 2025).

Refine's claim of finding problems in a third of refereed top-journal papers is unverified. I found nothing specific to behavioral economics.

### Cited Findings
- **Toda (June 2026) [PP].** Gemini, Refine, Claude and ChatGPT were tested on four published economic theory papers, each with an error the author helped find or fix. ChatGPT Pro did best, sometimes constructing counterexamples and corrected proofs. "No model located a true error without substantial human guidance." Training-data contamination complicates interpretation. A follow-up applied Gemini 3.5 Flash, Claude Opus 4.8 and ChatGPT 5.5 Pro to three more papers, including the incorrect original proof of Proposition 4 in Kocherlakota (1992). Refine cost about $50 per analysis — [arXiv 2606.05383](https://arxiv.org/pdf/2606.05383); [papers.cool](https://papers.cool/arxiv/2606.05383).
- **Havranek and Irsova (July 2026; arXiv 2607.14713, CEPR DP 21752, IES WP 19/2026) [PP].** Authors of 44 meta-analyses ranked three AI reports on their own papers. Reports were held to a common length and template, and author identities were masked; the design was pre-registered. A single frontier-model pass beat two multi-agent debate tools ("mad-research" and "paper-workshop") by 0.66 and 0.57 rank points, and paper-workshop used about 30 times the tokens. Authors who recognized their real referee report usually ranked it first, while AI judges almost always ranked it last — [EconPapers](https://econpapers.repec.org/RePEc:arx:papers:2607.14713); [IES summary](https://ies.fsv.cuni.cz/does-multi-agent-debate-improve-ai-feedback-research-papers); [CEPR](https://cepr.org/publications/dp21752).
- **Pataranutaporn, Powdthavee and Maes (IZA DP 17659, Jan 2025; arXiv 2502.00070) [PP].**
  - v1 reports 27,090 evaluations of 9,030 submissions with author traits and paper quality varied — [arXiv v1](https://arxiv.org/abs/2502.00070v1). Another version describes more than 29,000 evaluations of 1,220 anonymized papers from 110 economics journals — [search summary of IZA/arXiv v2](https://repec.iza.org/dp17659.pdf).
  - LLMs separated quality tiers in line with journal prestige; Claude and Gemma did best.
  - GPT, Gemma and LLaMA rated papers higher when attributed to top male authors and elite institutions.
  - The models struggled to tell top human papers from high-quality AI-generated ones — [IZA](https://iza.org/publications/dp/17659).
- **Brodeur et al. (I4R; IZA DP 17645, Jan 2025; PNAS 2026) [PR].** 288 researchers in 103 teams reproduced published quantitative social-science results. Reproduction rates were 94% for human-only teams, 91% for AI-assisted teams and 37% for AI-led teams. Human-only teams caught more major coding errors; AI-assisted teams caught 0.4 more per team than AI-led ones. AI-led teams did worse on robustness checks — [IZA DP 17645](https://docs.iza.org/dp17645.pdf); [Essex repository](https://repository.essex.ac.uk/43026/); [Tilburg](https://research.tilburguniversity.edu/en/publications/ai-assisted-teams-outperform-ai-led-teams-but-not-human-only-team/).
- **REPRO-Bench (ACL 2025) [PR].** 112 social-science papers with public reproduction reports; the best agent scored 21.4%. Later frontier models still did poorly, and PaperRepro claims a 21.9% relative gain — [arXiv 2507.18901](https://arxiv.org/pdf/2507.18901); [author blog](https://ddkang.substack.com/p/claude-45-opus-solves-core-bench); [PaperRepro, arXiv 2603.00058](https://arxiv.org/html/2603.00058).
- **Refine in economics [SR, 2nd].**
  - Several top-five journals are experimenting, and Golub claims problems in at least a third of refereed papers — [Marginal Revolution](https://marginalrevolution.com/marginalrevolution/2026/03/is-ai-currently-helping-economic-research.html).
  - Cochrane's positive anecdote — [Kling](https://arnoldkling.substack.com/p/john-cochrane-gets-ai-pilled).
  - An unverified claim that the AEA and the Econometric Society use it — [SocietySpeaks](https://societyspeaks.io/discussions/10721/solve-for-the-refine-equilibrium?lang=pt).
- **OpenAIReview's benchmark** includes one paper labeled "Economic Theory", "Targeting Interventions in Networks", with 6 Refine comments. Recall by LLM judge was 0% zero-shot, 17% local, 33% progressive and 50% progressive before consolidation — [REPORT.md](https://raw.githubusercontent.com/ChicagoHAI/OpenAIReview/HEAD/benchmarks/REPORT.md). Its examples folder holds an AI-generated difference-in-differences policy paper from the "Autonomous Policy Evaluation Project" (Claude Code) — [apep_0001.tex](https://raw.githubusercontent.com/ChicagoHAI/OpenAIReview/HEAD/examples/apep_0001.tex).
- **Bäckman's skills** target economics and finance journals and pre-analysis plans (AEA and EGAP registries). No accuracy data was found — [README](https://raw.githubusercontent.com/claesbackman/AI-research-feedback/HEAD/README.md).
- **Health economics.** An LLM assessing a reporting checklist agreed with human consensus 72.3–94.7% of the time, with AUC up to 0.96, but performance varied by item — [JHEOR](https://jheor.org/article/145214.pdf).
- **Other social-science context** (secondhand, from the ARS README):
  - *Organization Science* scored 6,957 submissions with an AI-writing classifier. Heavily AI-written manuscripts were desk-rejected more often. This is detection, not review — [ARS README](https://raw.githubusercontent.com/Imbad0202/academic-research-skills/HEAD/README.md).
  - A corpus audit estimated 146,932 hallucinated citations in 2025 across arXiv, bioRxiv, SSRN and PMC — [ARS README citing arXiv 2605.07723](https://raw.githubusercontent.com/Imbad0202/academic-research-skills/HEAD/README.md).
  - The Black Spatula Project lists PsyArXiv, SocArXiv and the Social Science Open Access Repository as paper sources but reports no social-science results — [README](https://raw.githubusercontent.com/The-Black-Spatula-Project/black-spatula-project/HEAD/README.md).

### Inferences
- For behavioral economics drafts, the riskiest READ checks are those needing deep judgment, which economics evidence shows AI does poorly unaided: LOG-07 math, LOG-08 design validity and MTH reproducibility. The checks most likely to work are mechanical and anchored: NUM-01, NUM-02, NUM-05, COH-02, CIT-01 and FMT. Recomputing a test from its statistic (NUM-03) also works, but behavioral economics usually reports regression tables (coefficients, standard errors, stars) rather than APA-style statistics. NUM-03 therefore needs a regression-table mode (t = b/SE, stars against p, N against degrees of freedom) alongside statcheck-style parsing.
- MTH and reproducibility checks should stay at "reporting completeness". They should not claim to verify reproduction, given 37% for AI-led reproduction and 21.4% on REPRO-Bench. If code is supplied, a paper–code alignment check in the style of Bäckman's `review-paper-code` is a reasonable optional extension.
- REV-04 personas reviewing economics papers should see an anonymized paper, because of the prestige and gender bias found in economics evaluations, and should not produce scores.
- The OpenAIReview example, "Targeting Interventions in Networks", is probably Galeotti, Golub and Goyal (Econometrica 2020), Golub being Refine's co-founder. I did not verify this.

### Gaps
- I found no evaluation on behavioral economics or experimental-economics papers specifically: lab or online experiments, preregistration, incentive compatibility, deception, or power.
- No independent accuracy study of Refine exists beyond Toda's four theory papers.
- No public data shows how Refine performs on empirical, as opposed to theory, economics papers.
- Agents4Science's subject mix and its reviewer-quality results were not retrieved.
- The exact Pataranutaporn sample sizes differ between versions and were not reconciled.
