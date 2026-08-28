![Poster Image](ASGH_2025/resized/IMG_9024_resized.jpg)

Title: Resolution of the D4Z4 repeat responsible for facioscapulohumeral muscular dystrophy with HiFi sequencing

1) COMPLETE TEXT EXTRACTION

Note: The poster image is readable but some fine text is partially obscured at this resolution. Unclear or uncertain words are flagged in brackets with a question mark, for example: [word?]. Verbatim text is preserved where legible.

- Title, authors, and affiliations
  - Resolution of the D4Z4 repeat responsible for facioscapulohumeral muscular dystrophy with HiFi sequencing
  - Authors (as legible): [Pooja Chawla?], [Peter K.??], [Konstantin?], Joseph M. [Dekker?], Jacek [???], Arel S. [Bortnyuk?], Shamia [Yusuf?], Solomon [Lynch?], Kelly [Nguyen?], Amanda S. [Liddy?], Egor Dolzhenko, Michael A. [Eberle?]
  - Affiliations: PacBio, Menlo Park, CA, USA; GenDx, Gaithersburg, MD, USA

- Introduction/Background (complete paragraphs)
  - The D4Z4 repeat is a variable number tandem repeat (VNTR) that contains some of the most [challenging?] loci in the human genome. D4Z4 has a repeat unit of 3.3 kb located on the subtelomeric regions of chromosome 4q and 10q.
  - Facioscapulohumeral muscular dystrophy (FSHD) results from derepression of DUX4. In FSHD1, contraction of the D4Z4 repeat on chromosome 4qA to 1–10 units on a permissive 4qA haplotype is pathogenic. In FSHD2, loss of methylation is due to epigenetic mechanisms such as SMCHD1 [and DNMT3B/LRIF1?] mutations that also derepress DUX4.
  - Genetic testing of the D4Z4 region is complicated by the high sequence similarity between 4q35 and 10q26, mosaicism, and rearrangements. The current gold standard for assessing D4Z4 copy number is Southern blotting, which is labor intensive and has limited resolution.
  - We show that high-accuracy long-read sequencing (PacBio HiFi) overcomes these challenges and, together with a computational tool, Kivvi, resolves D4Z4 using PacBio HiFi whole-genome sequencing (WGS). [Remaining sentences in this paragraph are partially unreadable.]

- Methods/Methodology
  - Section heading: Kivvi workflow
  - Text (as legible):
    - HiFi reads are aligned to the D4Z4 reference with unique flanks on chr4 and chr10.
    - Kivvi identifies unique sequence variants within each 3.3 kb repeat unit and clusters reads by array and haplotype.
    - For each D4Z4 array, Kivvi assembles phased haplotypes, counts repeat units, identifies 4qA/4qB haplotypes, and estimates methylation levels.
    - Outputs include fully assembled D4Z4 alleles, copy number, haplotype (4qA/4qB; 10qA/10qB), and methylation profiles per repeat unit.
    - [A QR code links to software or documentation; content not readable.]

- Results (all text, figure captions, and data labels)
  - Left panel: Figure 1 and Figure 2
    - Figure 1: Overview of the D4Z4 locus. D4Z4 arrays are on chromosomes 4q and 10q. The distal 4qA haplotype contains a polyadenylation signal that stabilizes DUX4 transcripts. [Subpanels labeled A, B, schematic arrows indicating 4qA/4qB and 10q arrays; precise labels partially unreadable.]
    - Figure 2: Unique copies of the D4Z4 repeat units in a sample. HiFi reads are aligned to the D4Z4 reference. Kivvi identifies variant repeat units and assembles allele-specific arrays. [Axis and legend text not readable.]
  - Center-left: Application of Kivvi in FSHD patient samples (bullet list)
    - 11 FSHD1 samples, allele size range [1–10?] units
    - [8?] samples from [North?] America; [Southern blot?] used for comparison
    - Samples with SMCHD1 variants consistent for FSHD2
    - [n=?] samples [with/without] Southern blot
    - 4,703 population samples from five ancestral populations
    - [Some bullets are partially unreadable; numbers marked where legible.]
  - Center: Figure 3, Figure 4, Figure 5 (methylation and assembly)
    - Figure 3: [Title unreadable]. Broad size and methylation levels of D4Z4 arrays across patients. [Dots/points represent repeat units; gray bars show methylation; exact labels not readable.]
    - Figure 4: Fully assembled D4Z4 alleles and their methylation levels. [Axis/caption text partially unreadable.]
    - Figure 5: [Sample-wise methylation plots?] Methylation levels of D4Z4 arrays in FSHD1 and controls. [Further caption text unclear.]
  - Right-top: Sequence analysis across populations
    - Figure 6: Distribution of D4Z4 alleles. (A) Copy number. (B) Prevalence of distal haplotypes on chr4 and chr10. [Y-axis labels not legible; legend shows colors for haplotypes.]
    - Figure 7: Principal component analysis of D4Z4 repeats based on sequence variants. Each dot is a D4Z4 repeat unit. All samples colored or labeled by [chromosome/haplotype/population]. [Axes not readable.]
  - Right-bottom: In cis duplications of D4Z4 arrays
    - Figure 8: Sample with [four?] D4Z4 arrays on chr4 due to in cis duplication. HiFi reads span duplication breakpoints and downstream [genes?]. [Remaining caption text partially unreadable.]
  - References (complete citations; as legible)
    - 1. Lemmers et al. A unifying genetic model for FSHD [journal/year unreadable].
    - 2. Lemmers et al. [Title includes DUX4]. [Details unreadable.]
    - 3. Mul et al. [Long-read sequencing identifies … FSHD]. [Details unreadable.]
    - 4. [Giardine?] et al. [Title unreadable].
    - 5. [Cao?] et al. [Title unreadable].
  - Any supplementary text, acknowledgments, or footnotes
    - Logos: PacBio; GenDx
    - Poster number on board: 4104 (conference board label, not part of poster content)
    - Acknowledgments: [Not visible]
    - Footnotes: [Not visible]

- For each figure, extract what is legible
  - Figure 1. Title: Overview of the D4Z4 locus
    - Axis labels: [schematic; no axes]
    - Legends/annotations: 4qA vs 4qB; 10q arrays; DUX4 at distal 4qA; 3.3 kb repeat units
    - Caption: Overview of the D4Z4 locus. D4Z4 arrays lie on chromosome 4q and 10q; the permissive 4qA haplotype contains a poly-A signal enabling DUX4 expression. [Some words unreadable]
  - Figure 2. Title: Unique copies of the D4Z4 repeat unit in a sample
    - Axis labels: [not legible]
    - Legends/annotations: HiFi read pileups; variant repeat units; allele-specific clustering
    - Caption: HiFi reads are assigned to the D4Z4 reference with unique flanks; Kivvi clusters and assembles repeats; methylation tracks per repeat unit. [partial]
  - Figure 3. Title: [Unreadable; methylation vs size summary]
    - Axis labels: [not legible]
    - Legends/annotations: Patient IDs on x-axis; methylation fraction on y-axis [inferred]; points for repeat units; shaded bands for arrays
    - Caption: Broad size and methylation levels of D4Z4 arrays across FSHD patients; Southern blot results shown for comparison. [partial]
  - Figure 4. Title: Fully assembled D4Z4 alleles and their methylation levels
    - Axis labels: [not legible]
    - Legends/annotations: arrays per haplotype; methylation tracks
    - Caption: [Partial; mentions assembly and methylation per repeat unit]
  - Figure 5. Title: [Unreadable; sample-wise methylation]
    - Axis labels/legends: [not legible]
    - Caption: Methylation levels of D4Z4 arrays for FSHD1 and [controls]; HiFi-based methylation calls. [partial]
  - Figure 6. Title: Distribution of D4Z4 alleles
    - Panels: (A) Copy number (violin plots) (B) Prevalence of distal haplotypes on chr4 and chr10 (stacked bars)
    - Axis labels: [not legible]
    - Legend: Colors for haplotypes (e.g., 4qA, 4qB, 10qA, 10qB)
    - Caption: Distribution of D4Z4 alleles: (A) Copy number. (B) Prevalence of distal haplotypes on chr4 and chr10. [partial]
  - Figure 7. Title: Principal component analysis of D4Z4 repeats based on sequence variants
    - Axis labels: PC1, PC2 [inferred from PCA]
    - Legend/annotations: clusters by chromosome/haplotype/population
    - Caption: Principal component analysis of D4Z4 repeats based on sequence variants. Each dot is a D4Z4 repeat unit. All samples colored by [chromosome/haplotype/population]. [partial]
  - Figure 8. Title: In cis duplications of D4Z4 arrays
    - Axis labels: [none; schematic]
    - Legends/annotations: multiple arrays in cis; arrows indicating duplication junctions
    - Caption: Sample with [four?] D4Z4 arrays on chr4 due to in cis duplication; HiFi reads support breakpoints and downstream configuration. [partial]

2) VISUAL ELEMENT DOCUMENTATION

- Figure 1: Schematic locus overview
  - Type: Genome schematic/workflow diagram
  - Patterns: Distinction of 4qA vs 4qB, and 10q arrays; DUX4 present only on 4qA
  - Color scheme: Distinct colors for haplotypes and repeat units
  - Axes: None (schematic)
  - Sample size: Not applicable

- Figure 2: Read pileup and repeat-unit uniqueness
  - Type: Read alignment/pileup tracks with repeat-unit annotation
  - Patterns: Recurrent 3.3 kb repeat units; unique variants within units allow clustering
  - Colors: Different colors for unit classes/haplotypes; grayscale for methylation track
  - Axes: Genomic coordinates along array (not legible)
  - Sample size: Single representative sample

- Figure 3–5: Patient methylation and assembly plots
  - Type: Scatter/line plots and per-array methylation tracks
  - Patterns: FSHD samples show contracted arrays and global hypomethylation vs controls
  - Colors: Points in gray/colored; methylation as grayscale/heat scale
  - Axes: Likely repeat number vs methylation fraction (0–1) [not legible]
  - Sample size: 11 FSHD1; additional FSHD2 and controls noted

- Figure 6: Population distributions
  - Type: (A) Violin plots/density plots of copy numbers; (B) Stacked bar charts of haplotype prevalence
  - Patterns: Broad distribution of copy numbers; clear differences in haplotype frequencies across chr4 vs chr10
  - Colors: Distinct colors per haplotype (e.g., 4qA/4qB/10qA/10qB)
  - Axes: Copy number on y-axis (in A); percentage frequency on y-axis (in B) [inferred]
  - Sample size: 4,703 genomes from five ancestral populations

- Figure 7: PCA of repeat variants
  - Type: Scatter plot (PCA)
  - Patterns: Distinct clusters corresponding to chromosome/haplotype states; likely separation of 4q vs 10q
  - Colors: Clusters colored by haplotype/population
  - Axes: PC1 and PC2 (unitless)
  - Sample size: Many repeat units across 4,703 samples

- Figure 8: In cis duplication map
  - Type: Structural variant schematic with read support
  - Patterns: Multiple D4Z4 arrays present on the same chromosome 4 in cis; long reads span junctions
  - Colors: Arrays in yellow; flanks/genes in different colors
  - Axes: Genomic coordinates (schematic)
  - Sample size: Single exemplar

Confidence for visual descriptions: medium (most elements are visible but small labels are not readable).

3) SCIENTIFIC CONTENT ANALYSIS

- Research question
  - Can high-fidelity long-read whole-genome sequencing (PacBio HiFi), combined with a dedicated analysis tool (Kivvi), fully resolve the pathogenic D4Z4 repeat arrays underlying FSHD, including copy number, haplotype (4qA/4qB; 10qA/10qB), methylation, and complex rearrangements? Confidence: high.

- Novel approach
  - Use of HiFi WGS to reconstruct D4Z4 arrays end-to-end with base-level sequence, allelic phasing, and per-unit methylation, replacing or augmenting Southern blotting and targeted assays. The Kivvi tool appears to leverage unit-specific variants within the 3.3 kb D4Z4 repeat to cluster and assemble arrays and to type distal haplotypes. Confidence: high.

- Key findings (3–5)
  1) HiFi + Kivvi resolves D4Z4 arrays, accurately infers copy number and distinguishes 4qA/4qB and 10q haplotypes in FSHD patients and population samples. Confidence: high.
  2) FSHD1 samples show contracted 4qA arrays (approximately 1–10 repeats) and hypomethylation relative to controls; per-unit methylation profiles are recoverable from HiFi data. Confidence: medium-high.
  3) Large-scale population analysis (n=4,703) shows the distribution of D4Z4 copy numbers and haplotypes across five ancestral populations and reveals sequence-variant structure that clusters by chromosome/haplotype. Confidence: high.
  4) HiFi detects complex configurations, including in cis duplications of D4Z4 arrays that are challenging for traditional assays. Confidence: medium-high.

- Technical significance
  - Clinically relevant VNTR resolution in a medically important locus using WGS enables a single comprehensive assay for FSHD diagnostics and research: copy number, haplotype phase, methylation, and structural variants. It reduces reliance on Southern blotting, improves detection of mosaicism and complex rearrangements, and provides population reference data. Confidence: high.

- Methodology strengths
  - High per-base accuracy of HiFi reads across repeats; allele-specific assembly using unit-level variants; direct methylation estimation from kinetics/signals; orthogonal comparison to Southern blot; scalable to thousands of genomes. Confidence: high.

4) DATA INTERPRETATION

- Result: Accurate determination of D4Z4 copy number and haplotype
  - Interpretation: The method distinguishes pathogenic 4qA contractions from benign 4qB/10q arrays, an essential step in FSHD diagnostics. Confidence: high.
  - Statistical significance: Not explicitly shown, but large n=4,703 population set supports robust haplotype frequency estimation. Confidence: medium.
  - Hypothesis link: Resolving copy number and haplotype confirms that contraction on a permissive 4qA background is the FSHD1 lesion. Confidence: high.
  - Limitations: Exact accuracy metrics, error rates, and benchmarks vs Southern blot are not visible. Confidence: medium.

- Result: Methylation profiling across repeat units
  - Interpretation: FSHD1 alleles are hypomethylated across D4Z4 compared to controls; per-unit methylation tracks reveal patterns consistent with epigenetic derepression. Confidence: medium-high.
  - Significance: Hypomethylation is a hallmark of FSHD1 and FSHD2; capturing it in WGS adds functional context. Confidence: high.
  - Limitations: Detailed numeric methylation levels, statistical tests, and control sample counts are not readable. Confidence: medium.

- Result: Population distribution and sequence-variant structure
  - Interpretation: Copy number and haplotype frequencies vary; PCA of unit variants shows separable clusters, suggesting stable, haplotype-specific sequence signatures. Confidence: high.
  - Significance: Provides a population baseline for interpreting patient results and for understanding locus evolution. Confidence: high.
  - Limitations: Axes scales and variance explained by PCs are not visible. Confidence: medium.

- Result: Detection of in cis duplications
  - Interpretation: HiFi reads span complex duplications leading to multiple D4Z4 arrays on chromosome 4; these could confound traditional tests and may affect risk interpretation. Confidence: medium-high.
  - Significance: Demonstrates advantage of long reads in structural variant characterization at repetitive loci. Confidence: high.
  - Limitations: Prevalence and clinical impact not quantified here. Confidence: medium.

5) CONTEXTUAL UNDERSTANDING

- Field context
  - Area: Medical genomics of tandem repeats; neuromuscular genetics; structural variant analysis with long reads; epigenomics of FSHD. Confidence: high.

- Clinical/practical relevance
  - A single WGS-based assay could replace multi-step testing (Southern blot + haplotyping + methylation assays), accelerating diagnosis, enabling detection of mosaicism/complex rearrangements, and informing genetic counseling. Confidence: high.

- Related work (based on references)
  - Foundational studies defining D4Z4 contraction on 4qA as causal (Lemmers et al.), the role of DUX4, and epigenetic modifiers (SMCHD1 and others). This poster extends by providing comprehensive long-read resolution and population-scale characterization. Confidence: medium (exact citations unreadable).

- Future directions
  - Validate in clinical cohorts with blinded comparison to gold standard; report sensitivity/specificity; integrate with variant calling for SMCHD1/DNMT3B/LRIF1; expand to trio analyses and mosaicism quantification; standardize reporting for clinical use. Confidence: high.

6) TECHNICAL DETAILS

- Sample sizes and populations
  - Patients: 11 FSHD1 samples; additional FSHD2 (SMCHD1) carriers; some with Southern blot comparisons. Confidence: medium (exact counts partially unreadable).
  - Population dataset: 4,703 individuals across five ancestral populations. Confidence: high.

- Techniques/technologies/tools
  - PacBio HiFi whole-genome sequencing
  - Kivvi computational tool for D4Z4 analysis (repeat-unit variant clustering, allele assembly, haplotype typing, methylation estimation)
  - Southern blot used orthogonally in a subset. Confidence: high.

- Statistical methods mentioned
  - Principal component analysis (PCA) of repeat-unit sequence variants. Confidence: high.
  - Distribution summaries (violin plots, stacked bars). Statistical tests not explicitly readable. Confidence: low.

- Software/databases/computational approaches
  - Kivvi (poster-specific tool); likely uses alignment to custom D4Z4 references with unique flanks; phasing/assembly via unit-variant signatures; methylation calls from HiFi kinetics. Confidence: medium.

- Quality control measures
  - Orthogonal confirmation in “FSHD patient samples” by Southern blot; per-unit methylation consistency across reads; haplotype assignment using distal sequence (4qA/4qB). Confidence: medium.

7) WORKFLOW RECONSTRUCTION

- Step-by-step pipeline (from “Kivvi workflow” and figures)
  1) Generate PacBio HiFi WGS reads for each sample.
  2) Align HiFi reads to a D4Z4 locus reference containing unique upstream/downstream flanks for chr4 and chr10.
  3) Identify sequence variants within each 3.3 kb D4Z4 repeat unit; cluster reads into arrays by chromosome and haplotype.
  4) Assemble phased arrays per allele; count repeat units to determine copy number.
  5) Determine distal haplotype (4qA vs 4qB; 10qA vs 10qB) from terminal sequence (e.g., pLAM/poly-A-bearing 4qA).
  6) Estimate CpG methylation levels per repeat unit directly from HiFi signals.
  7) Report per-sample outputs: allele copy numbers, haplotypes, methylation profiles, and detection of structural rearrangements (e.g., in cis duplications).
  8) Optionally compare with Southern blot or other orthogonal assays for validation.

Confidence: high for steps 1–6; medium for implementation details.

8) QUALITY ASSESSMENT

- Clarity of presentation
  - Strong high-level organization with clear sectioning (Introduction, Workflow, Applications, Population analysis, Duplications). Figures are informative; some fine text is dense. Confidence: high.

- Completeness of methodology description
  - Core algorithmic steps are described; explicit parameter settings, accuracy metrics, and benchmarking details are limited on the poster. Confidence: medium.

- Strength of conclusions relative to data shown
  - Figures support claims of assembly, haplotyping, methylation profiling, and detection of complex events; large population analysis adds weight. Absent are detailed performance statistics (sensitivity/specificity). Confidence: medium-high.

- Gaps/unanswered questions
  - Exact concordance vs Southern blot; handling of somatic mosaicism; per-sample coverage requirements; turnaround time; error modes; clinical reporting guidelines. Confidence: high.

9) TERMINOLOGY GLOSSARY

- D4Z4: A 3.3 kb tandem repeat unit present in arrays at 4q35 and 10q26; pathogenic when contracted on a permissive 4qA haplotype. Confidence: high.
- VNTR: Variable number tandem repeat; loci composed of repeating units with variable copy number. Confidence: high.
- FSHD (Facioscapulohumeral muscular dystrophy): A muscular dystrophy caused by DUX4 derepression due to D4Z4 contraction (FSHD1) or epigenetic defects (FSHD2). Confidence: high.
- FSHD1: Form caused by contraction of the 4qA D4Z4 array to 1–10 repeats on a permissive 4qA haplotype. Confidence: high.
- FSHD2: Form caused by mutations in epigenetic regulators (e.g., SMCHD1, DNMT3B, LRIF1) leading to hypomethylation of D4Z4 and DUX4 expression. Confidence: high.
- DUX4: A transcription factor encoded distal to D4Z4 on 4qA; its stabilized expression is toxic to muscle. Confidence: high.
- 4qA/4qB: Distal haplotypes at chromosome 4q; 4qA includes a poly-A signal enabling pathogenic DUX4 expression; 4qB is considered non-permissive. Confidence: high.
- 10qA/10qB: Analogous haplotypes on chromosome 10q; generally non-pathogenic. Confidence: high.
- HiFi sequencing: PacBio circular consensus long-read sequencing with high per-base accuracy (~Q20–Q30+). Confidence: high.
- PCA: Principal component analysis; a dimensionality reduction technique to visualize variant patterns. Confidence: high.
- In cis duplication: Duplication events on the same chromosome copy, here generating multiple D4Z4 arrays on chr4. Confidence: high.
- Southern blot: A DNA method historically used to size D4Z4 arrays; labor-intensive and lower resolution than long-read sequencing. Confidence: high.

10) SYNTHESIS

- Executive summary for a non-specialist
  - This poster addresses a long-standing challenge in diagnosing a form of muscular dystrophy (FSHD) that is caused by changes in a repetitive DNA region called D4Z4. Traditional tests struggle to measure the size and structure of this repeat because it is highly repetitive and looks similar on two chromosomes. The authors use PacBio HiFi whole-genome sequencing, which produces long, accurate DNA reads, and introduce a software tool called Kivvi to assemble the repeat, determine the exact copy number, identify the disease-relevant haplotype, and even measure DNA methylation (a chemical modification) across the repeat.

  - Applying this approach to patient samples, they show that it identifies the hallmark features of FSHD1 (a contracted 4qA array with low methylation) and captures complex configurations like duplicated arrays that are difficult to detect with older methods. They also analyze 4,703 genomes from diverse populations to describe how D4Z4 repeat sizes and haplotypes are distributed and to reveal distinct sequence patterns across chromosomes and haplotypes.

  - The work suggests that a single whole-genome sequencing test can deliver comprehensive information needed for FSHD genetics—copy number, haplotype, methylation, and structural variants—potentially replacing multiple legacy assays. This could streamline diagnostics, uncover complex cases, and build better population references, ultimately improving patient care and research into disease mechanisms.

Overall confidence in content interpretation: medium-high (core claims and figures are clear; some fine-grained text and numeric details are not readable at this image resolution).