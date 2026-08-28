import json
import re

# This data structure holds the content extracted from your uploaded documents.
# In a real application, you would typically read this from the files.
# For this script, I am including the extracted content directly for demonstration.
file_data = {
    "IMG_1245_resized.md": {
        "title": "Occurrence of norovirus and other viral gastroenteritis pathogens in sporadic Medically Attended Acute Gastroenteritis Kaiser Permanente Northwest members, 2023-2024",
        "main_takeaway": "The study highlights the ongoing occurrence of norovirus and other viral pathogens as significant contributors to acute gastroenteritis in a specific cohort, underscoring the need for continued monitoring and preventive measures within the community.",
        "detailed_summary": "The poster presents research on the incidence of norovirus and other viral pathogens associated with medically attended acute gastroenteritis among Kaiser Permanente Northwest members from late 2023 to October 2024. It details the methodology used to gather data, including participant enrollment and the timeline of the study, which spanned from November 2023 to October 2024. Key results include the identification of viral pathogens in positive samples, with specific attention to the variations in prevalence among different age groups, locations, and over time. The poster includes graphs and charts that illustrate the frequency and types of pathogens detected, as well as phylogenetic analysis to understand the genetic makeup of norovirus strains.",
        "keywords": [
            "Norovirus",
            "Gastroenteritis",
            "Viral pathogens",
            "Kaiser Permanente",
            "Epidemiology",
            "Public health",
            "Phylogenetic analysis",
            "Acute gastroenteritis",
        ],
    },
    "IMG_1244_resized.md": {
        "title": "Enhancement of Carbapenemase Producing Organism Colonization Screening Workflow: Decreasing Time, Increasing Data, and Maximizing Resource Capabilities",
        "main_takeaway": "The poster emphasizes that the enhanced CPO screening workflow significantly reduces reporting times while increasing the volume and reliability of screening data, thus improving patient management and control of antibiotic resistance.",
        "detailed_summary": "The poster outlines enhancements to the screening workflow for Carbapenemase Producing Organisms (CPO) in a laboratory setting, highlighting a structured approach to improve efficiency and resource utilization. Key points include:\n\n- **Introduction**: Describes the importance of timely detection of CPOs to manage antibiotic resistance, stressing that traditional methods were too slow.\n- **Methods**: Details the Wadsworth Center's CPO screening process, illustrating the workflow from specimen collection to reporting results. It employs rapid PCR techniques to screen for specific CPO genes.\n- **Data Analysis**: Presents graphs showing the turnaround time for screening from 2018 to 2023, indicating improvements in efficiency and cost. It also outlines the contributions of pre-analytical, analytical, and post-analytical phases to overall turnaround time.\n- **Conclusions**: Summarizes that the optimized workflow enables rapid reporting of results, often within 24 hours, compared to previous methods taking several days.",
        "keywords": [
            "Carbapenemase",
            "Screening Workflow",
            "Antimicrobial Resistance",
            "Workflow Optimization",
            "PCR Techniques",
            "Turnaround Time",
            "Laboratory Efficiency",
        ],
    },
    "IMG_1243_resized.md": {
        "title": "Implementation of Illumina Clarity LIMS: Experiences and Perspectives from the NC Public Health Lab",
        "main_takeaway": "The primary message of the poster is that implementing Clarity LIMS has significantly improved the efficiency, data management, and accuracy of sample tracking at the North Carolina Public Health Lab, enabling better public health outcomes.",
        "detailed_summary": "The poster discusses the implementation of the Illumina Clarity Laboratory Information Management System (LIMS) at the North Carolina State Laboratory of Public Health. It details various aspects such as the project's background, methodologies for integrating LIMS, results obtained, and significance. Key points include:\n\n- **Abstract**: Outlines the purpose of implementing Clarity LIMS to enhance sample processing and tracking capabilities.\n- **Introduction**: Describes the importance of LIMS in managing sequencing data and streamlining workflows.\n- **Methods**: Provides insight into the steps taken to integrate samples and track projects within the LIMS.\n\n- **Results**: Highlights successful integration achieved through Clarity LIMS, emphasizing improvements in efficiency and data tracking.\n- **Significance**: Discusses the benefits of LIMS in reducing human error and ensuring data integrity.\n- **Challenges**: Mentions potential issues related to software updates and integration with existing systems.\n- **Acknowledgments** and **Resources**: Acknowledges contributors and provides additional resources for further information.",
        "keywords": [
            "Illumina",
            "Clarity LIMS",
            "Sample Tracking",
            "Public Health",
            "Laboratory Information Management",
            "Data Integration",
            "Workflow Efficiency",
            "Human Error Reduction",
            "Sequencing Data",
        ],
    },
    "IMG_1242_resized.md": {
        "title": "Enhancement of Newborn Screening Reporting Interpretations for Severe Combined Immunodeficiency (SCID) in North Carolina",
        "main_takeaway": "The most important message conveyed by this poster is that through systematic improvements in reporting and follow-up processes, newborn screening for SCID in North Carolina has become more effective, helping to ensure timely interventions for affected infants.",
        "detailed_summary": "The poster presents research on improving newborn screening methods for Severe Combined Immunodeficiency (SCID) in North Carolina. It outlines a timeline for the implementation of newborn screening (NBS) for SCID, noting that it was introduced in 2017 using lab-developed tests to measure T-cell receptor excision circles (TRECs) and ribonuclease P (RNAse P). By 2021, the screening methods were further developed, and reporting protocols were revised to ensure better population data use.\n\nKey initiatives were discussed that include:\n- Addition of abnormal urgent interpretations.\n- Strategies based on gestational age to refine screenings.\n- Updated algorithms for managing follow-up recommendations.\n\nResults illustrated in the form of graphs show trends in TREC values over time, indicating that adjustments to the initial algorithm led to increased follow-up reports for abnormal cases. This showcases a more tailored and efficient approach to dealing with SCID detection.",
        "keywords": [
            "Newborn Screening",
            "Severe Combined Immunodeficiency (SCID)",
            "TREC",
            "Quality Improvement",
            "Screening Algorithm",
            "Public Health",
        ],
    },
    "IMG_1241_resized.md": {
        "title": "Genomic Diversity, Antibiotic Resistance, and Stress Adaptation of Salmonella Isolates: Insights from a Four-Year Surveillance Study in New Hampshire",
        "main_takeaway": "The most important message conveyed by the poster is that genomic surveillance is crucial for understanding the genetic diversity, antibiotic resistance, and stress response of Salmonella, ultimately aiding public health efforts to manage and mitigate risks associated with this pathogen.",
        "detailed_summary": "The poster presents findings from a genomic surveillance study of 684 Salmonella isolates collected over four years (2020-2023) in New Hampshire. It emphasizes the importance of genomic analysis in understanding the genetic diversity and antibiotic resistance of Salmonella, which poses a significant public health risk. Key elements of the research include:\n\n- **Introduction**: Highlights Salmonella's status as a major public health concern, emphasizing the need for effective genomic surveillance to monitor this pathogen and its resistance patterns.\n- **Materials and Methods**: Discusses the use of paired-end FASTQ files from various sources, processed using tools such as NCBI accessioning, and various software for analysis (e.g., Python, R). The methodology focuses on whole-genome sequencing and bioinformatics to assess genetic variations and relationships among isolates.\n- **Results**: Presents findings on genetic relationships among isolates, variations in antibiotic resistance, and stress adaptations. The analysis shows a robust correlation between genetic diversity and resistance mechanisms.\n\n- **Significance**: Underlines the role of genomic surveillance in tracking Salmonella dynamics and aiding public health interventions.\n- **Acknowledgements**: Recognizes support from cooperative agreements and institutions involved in the study.",
        "keywords": [
            "Genomic Surveillance",
            "Salmonella",
            "Antibiotic Resistance",
            "Bioinformatics",
            "Public Health",
            "Whole-Genome Sequencing",
            "Isolate Diversity",
            "Stress Adaptation",
            "New Hampshire",
        ],
    },
    "IMG_1240_resized.md": {
        "title": "Rare case of septicemia caused by Salmonella enterica serotype Gaminara linked to exposure to a pet bearded dragon",
        "main_takeaway": "The key message conveyed by the poster is the identification of a rare Salmonella Gaminara infection linked to a pet, emphasizing the necessity for enhanced awareness and understanding of zoonotic disease transmission from reptiles to humans.",
        "detailed_summary": "The poster discusses a rare case of septicemia resulting from exposure to Salmonella enterica serotype Gaminara, which was linked to a pet bearded dragon. The introduction explains that salmonellosis can be contracted from reptiles, with bearded dragons being potential carriers. Methodologically, the study employed a standardized questionnaire to gather information on the patient's symptoms and risk factors. Clinical and microbiological assessments confirmed the presence of the bacteria. \n\nThe case report details an adolescent presenting with serious symptoms including septicemia, which prompted further testing. Blood and stool samples were collected, leading to the identification of Salmonella in both. Advanced techniques such as whole genome sequencing (WGS) were utilized to analyze the bacterial strains present, revealing multiple strains in the patient's test samples. The significance of the study lies in demonstrating the importance of WGS in tracing the source of infection and implementing public health interventions.",
        "keywords": [
            "Salmonella enterica",
            "Septicemia",
            "Bearded dragon",
            "Zoonotic disease",
            "Whole genome sequencing",
            "Bacteriology",
            "Public health",
        ],
    },
    "IMG_1239_resized.md": {
        "title": "BERYLLIUM EXPOSURE AND WORKPLACE MEDICAL SURVEILLANCE",
        "main_takeaway": "The most important message conveyed by the poster is that regular medical surveillance and early detection are crucial for protecting workers from the health risks associated with beryllium exposure.",
        "detailed_summary": "The poster outlines critical information about beryllium, a lightweight, highly toxic metal used in various industries, including aerospace and electronics. It discusses beryllium's properties, health risks associated with exposure, and the importance of medical surveillance for workers exposed to the substance. Key points include:\n\n- **Characteristics of Beryllium**: Highlighting its lightweight nature and applications in various fields, such as aerospace and nuclear energy.\n- **Health Risks**: Emphasizes the dangers of beryllium exposure, which can lead to serious lung conditions, notably Chronic Beryllium Disease (CBD) and Beryllium Sensitization (BeS).\n- **Medical Surveillance**: Details the necessity of regular medical check-ups to detect early symptoms and sensitization to beryllium through the BeLPT test.\n- **Risk Factors**: Notes the estimated number of workers at risk and emphasizes the need for workplace medical surveillance.\n\n- **Prevention Strategies**: Provides strategies for reducing exposure and ensuring health monitoring.",
        "keywords": [
            "Beryllium",
            "Exposure",
            "Medical Surveillance",
            "Chronic Beryllium Disease (CBD)",
            "Beryllium Sensitization (BeS)",
            "BeLPT test",
            "Workplace safety",
            "Health risks",
        ],
    },
    "IMG_1238_resized.md": {
        "title": "Rapid Detection and Response to a Local B. melitensis Outbreak in North Carolina",
        "main_takeaway": "The most important message conveyed by the poster is the necessity of rapid detection and response measures for effectively managing B. melitensis outbreaks to safeguard public health through well-coordinated laboratory testing and risk assessment approaches.",
        "detailed_summary": "The poster outlines the methods and findings related to the rapid detection and response to an outbreak of *Brucella melitensis* in North Carolina. It includes background information on the disease caused by *B. melitensis*, which can lead to zoonotic infections. The poster describes sentinel laboratory testing protocols, risk assessments for laboratory exposure, and recommendations for handling potential exposure. Key figures illustrate transmission pathways, testing results, and molecular analysis using reference testing from the North Carolina State Laboratory of Public Health (NCSLPH) and the Centers for Disease Control and Prevention (CDC). The conclusion emphasizes the importance of timely identification and effective response strategies to manage outbreaks and protect public health.",
        "keywords": [
            "Brucella melitensis",
            "Outbreak response",
            "Sentinel laboratory testing",
            "Risk assessment",
            "Public health safety",
            "Molecular analysis",
            "North Carolina",
            "Laboratory testing protocols",
        ],
    },
    "IMG_1237_resized.md": {
        "title": "Applying a Sample Size Calculation Framework to Evaluate and Improve SARS-CoV-2 Variant Surveillance in Massachusetts",
        "main_takeaway": "Utilizing the phylo-samp framework allows for improved understanding and management of sample size requirements in viral surveillance, thereby enhancing detection and response capabilities for SARS-CoV-2 variants.",
        "detailed_summary": "The poster presents research conducted by Z. Thompson and colleagues, focusing on improving surveillance of SARS-CoV-2 variants in Massachusetts. The study uses the phylo-samp framework to determine the necessary sample size for effective variant detection, addressing challenges related to variant prevalence and the need for confidence in results.\n\n### Background\n- The Massachusetts Department of Public Health monitors SARS-CoV-2 variants and their prevalence.\n- Accurate sampling is necessary to enhance surveillance and respond to variant changes.\n  \n### Objectives\n- To establish desired prevalence thresholds for variant detection and calculate the confidence in discovering variants at various prevalence levels.\n\n### Methods\n- Data were collected from state submissions, utilizing the R package phylo-samp.\n- Sampling was conducted on a weekly basis with analyses of detection ratios and estimations of sample sizes based on observed variants.\n\n### Results\n- The research found that consistent weekly sampling improved detection confidence.\n- Various graphs depict sample size needed for different prevalence targets and confidence levels.\n\n### Conclusions\n- The framework proved successful in assessing surveillance needs.\n- Recommendations include adjustments to sampling strategies in response to variant prevalence dynamics.",
        "keywords": [
            "SARS-CoV-2",
            "Variant Surveillance",
            "Sample Size Calculation",
            "phylo-samp Framework",
            "Public Health",
            "Massachusetts",
        ],
    },
    "IMG_1236_resized.md": {
        "title": "Measurement of BHA, t-BHQ, and phase II metabolites (t-BHQ-glucuronide and –sulfate) in serum by LC-MS/MS",
        "main_takeaway": "The study successfully validates an LC-MS/MS method for accurately measuring BHA and its metabolites in serum, which is crucial for monitoring food safety and animal health.",
        "detailed_summary": "The poster presents research focused on developing and validating an LC-MS/MS method to measure BHA and its metabolites in serum. The objective was to optimize the extraction and quantification processes for these compounds, which are prevalent in various food products and can affect animal health. The introduction outlines the relevance of BHA and its metabolites, particularly in food safety contexts. The method employed includes a liquid-liquid extraction (LLE) procedure to prepare serum samples, and the results demonstrate successful validation of this method for clinical and spiked samples. Key findings include optimized quantification parameters and validation of the extraction process, as shown through standard curves and analytical precision data. Discussion points include potential limitations and future directions for further studies, particularly involving beta-glucuronidase and sulfatase.",
        "keywords": [
            "BHA",
            "LC-MS/MS",
            "Metabolites",
            "Serum Analysis",
            "Food Safety",
            "Extraction Procedure",
            "Validation",
            "Toxicology",
        ],
    },
}

# Define clusters based on keywords and themes
clusters = {
    "Infectious Disease Surveillance & Outbreak Response": [
        "IMG_1245_resized.md",  # Norovirus
        "IMG_1241_resized.md",  # Salmonella Genomic Surveillance
        "IMG_1240_resized.md",  # Salmonella Case Report
        "IMG_1238_resized.md",  # Brucella melitensis Outbreak
        "IMG_1237_resized.md",  # SARS-CoV-2 Surveillance
    ],
    "Laboratory Methods & Efficiency": [
        "IMG_1244_resized.md",  # CPO Screening Workflow
        "IMG_1243_resized.md",  # LIMS Implementation
        "IMG_1236_resized.md",  # LC-MS/MS Method
    ],
    "Newborn Screening": [
        "IMG_1242_resized.md"  # SCID Screening
    ],
    "Environmental & Occupational Health": [
        "IMG_1239_resized.md"  # Beryllium Exposure
    ],
}

mind_map_data = {"name": "Public Health Documents Overview", "children": []}

for cluster_name, file_list in clusters.items():
    cluster_node = {"name": cluster_name, "children": []}
    for file_name in file_list:
        data = file_data.get(file_name)
        if data:
            document_node = {"name": data["title"], "children": [], "file": file_name}

            if data["main_takeaway"]:
                document_node["children"].append(
                    {
                        "name": "Main Takeaway",
                        "children": [{"name": data["main_takeaway"]}],
                    }
                )

            if data["detailed_summary"]:
                document_map_node = {"name": "Detailed Summary", "children": []}
                # Split detailed summary into manageable chunks or bullet points if any
                summary_points = [
                    point.strip()
                    for point in re.split(
                        r"\n- \*\*(.*?)\*\*:|\n- |\n", data["detailed_summary"]
                    )
                    if point and point.strip()
                ]

                current_major_point = None
                for point in summary_points:
                    major_point_match = re.match(r"\*\*(.*?)\*\*", point)
                    if major_point_match:
                        current_major_point = {
                            "name": major_point_match.group(1).strip(),
                            "children": [],
                        }
                        document_map_node["children"].append(current_major_point)
                    elif current_major_point:
                        if point.startswith("- "):
                            current_major_point["children"].append(
                                {"name": point[2:].strip()}
                            )
                        else:
                            current_major_point["children"].append(
                                {"name": point.strip()}
                            )
                    else:
                        document_map_node["children"].append({"name": point.strip()})

                if document_map_node["children"]:
                    document_node["children"].append(document_map_node)

            if data["keywords"]:
                keyword_node = {"name": "Keywords", "children": []}
                for keyword in data["keywords"]:
                    keyword_node["children"].append({"name": keyword})
                document_node["children"].append(keyword_node)

            cluster_node["children"].append(document_node)
    mind_map_data["children"].append(cluster_node)


with open("mindmap_data.json", "w") as f:
    json.dump(mind_map_data, f, indent=4)
print("Mind map JSON file generated successfully.")
