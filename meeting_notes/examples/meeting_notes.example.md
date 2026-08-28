# Meeting Notes 
Date: 2024-06-20
participants: Gilad, Rebecca, Mike, Colleen, Karen


## Project Updates
- Gilad is working with Rebecca on editing the volcano plot, removing less expressed genes to focus only on hemoglobin transcripts for the poster
- The team is finalizing an email response that will include the full DE output table as an attachment
- The table will also be uploaded to Cloud Hub for future reference

## Assembly Status
- Verko/DecoAssembly is currently running on the Soho server (New York)
- Coverage statistics for the trio:
    - Mother: 44x coverage, 70kb
    - Proband: 32x coverage, 75kb
    - Sibling: 35x coverage
- The graph alignment step is only using one thread, causing slow processing

## Neurodegenerative Disorder Case Study
- The team is working on a case involving progressive neurodegenerative disorder beginning in childhood
- Two siblings are affected (UDP-1904 older sister deceased at 26, and proband)
- Both showed normal early development followed by regression and cognitive decline
- Family includes unaffected parents and multiple unaffected siblings (including three fraternal triplet brothers)
- The team has mapping information and case summary but needs to confirm details about which family members are affected 


## Technical Discussion on Repeat Unit Analysis
- Gilad is working on an approach to identify repeat units using k-means clustering
- Current implementation identifies 3-4 clusters of repeat units, but this may be too few
- The method uses VG graph to analyze the clustered repeat units
- Discussion about the trade-offs between this approach and pre-correction methods
- Current testing shows the approach identifying approximately 57-65 repeats compared to the benchmark

## Action Items
[ ] Upload the Excel data table to Cloud Hub
[ ] Confirm the affected status of family members in the case study
[ ] Check methylation data for the samples
[ ] Look at workflow human bar outputs for obvious findings
[ ] Run D4Z4 end-to-end on ULK data as a comparison
[ ] Organize the folder structure containing ULK data for the four cell lines
[ ] Continue monitoring the assembly process
