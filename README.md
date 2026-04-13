# Bias-in-Robes-Detecting-Bias-Laundering-in-LLM-Generated-Judicial-Justifications-
Detecting Bias Laundering in Judicial LLMs: Framework, CJP Benchmark, and Automated Evaluation Protocol for Generative Legal Reasoning.

[![Conference](https://img.shields.io/badge/ICAIL-2026-blue.svg)](https://icail2026.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)

## 📖 Introduction

As Large Language Models (LLMs) become deeply integrated into judicial systems, they are shifting from assistive information retrieval to automatically generating legal judgments. This research reveals a hidden risk termed **"Bias Laundering"**—a process where LLMs leverage legal rhetoric and logical reasoning to transform non-legal biases into seemingly legitimate legal justifications.

We propose the **"Bias in Robes"** framework, an automated detection tool designed to stress-test the legal integrity of generative judicial reasoning models.

## 🌟 Key Features

* [cite_start]**CJP Benchmark**: The **Counterfactual Judicial Prompt (CJP)** dataset, comprising **4,256** counterfactual samples derived from 152 "hard cases" across 7 bias dimensions (Education, Ethnicity, Gender, etc.)[cite: 163, 507].
* [cite_start]**Bias Laundering Score (BLS)**: A quantitative 5-point metric to assess the severity of alignment failure, ranging from *Reject Bias* to *Amplify Bias*[cite: 557, 683].
* [cite_start]**Automated Evaluation Protocol**: An LLM-as-a-Judge paradigm implementing a **Chain-of-Thought (CoT) Decision Tree** (Existence Check $\rightarrow$ Attitude Check $\rightarrow$ Expansion Check $\rightarrow$ Weight Test)[cite: 586, 638].

## 📊 Main Findings

[cite_start]Our experimental results across models like GPT-5, Qwen3, and ChatLaw identified three failure modes[cite: 705, 1035]:
1.  [cite_start]**Laundering Gap**: SOTA models maintain robust defenses against *explicit* bias but remain highly susceptible to *implicit* induction[cite: 58, 1044].
2.  [cite_start]**Confirmation Bias**: Models often reinforce pre-existing social stereotypes rather than adhering to neutral law (Sycophancy Gap)[cite: 1051, 1055].
3.  [cite_start]**The "Mercenary" Trap**: Domain-specific fine-tuning (e.g., ChatLaw) may enhance technical legal synthesis while decoupling reasoning from normative evaluation, leading to procedural over-compliance[cite: 1058, 1096].

## 📂 Repository Structure

```text
├── data/
│   ├── CJP_benchmark.json       # Full dataset of 4,256 counterfactual samples
│   └── hard_cases_metadata.csv  # Metadata for the 152 base judicial cases
├── prompts/
│   ├── phase1_generation.md     # Phase 1: Bias-Inducing Generation templates
│   └── phase2_detection.md      # Phase 2: CoT Decision Tree Auditor templates
├── src/
│   ├── inference.py             # Code to generate judicial justifications
│   └── auditor.py               # Automated evaluation script (based on DeepSeek-V3)
├── LICENSE                      # Apache 2.0
└── README.md
