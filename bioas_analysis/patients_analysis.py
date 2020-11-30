import os
from datetime import date
from utils import *
from generate_embedding import *

base_datasets_dir = os.getcwd() + "/cancer_data/"
base_results_dir = os.getcwd() + "/results/cancer-{}/".format(str(date.today()))
if not os.path.exists(base_results_dir):
  os.makedirs(base_results_dir)
subset_links_scm = base_results_dir + "subset-links.scm"
attraction_links_scm = base_results_dir + "attraction-links.scm"

def populate_atomspace(atomspace):
  print("--- Populating the AtomSpace")
  scheme_eval(atomspace, "(load-file \"cancer_data/normalized_patient_8gene_over_expr.scm\")")
  scheme_eval(atomspace, "(load-file \"cancer_data/normalized_patient_8gene_under_expr.scm\")")
  scheme_eval(atomspace, "(load-file \"cancer_data/subset-bp-patient-overexpr_8genes.scm\")")
  scheme_eval(atomspace, "(load-file \"cancer_data/subset-bp-patient-underexpr_8genes.scm\")")  
  scheme_eval(atomspace, "(load-file \"cancer_data/patient_data_state&preTX.scm\")")
  # scheme_eval(atomspace, "(load-file \"cancer_data/sample_patient_615289.scm\")")   

def preprocess(atomspace):
  for e in atomspace.get_atoms_by_type(types.EvaluationLink):
    if e.tv.mean == 0:
      scheme_eval(atomspace,"(cog-delete {})".format(e))

def apply_subset_rule1(atomspace):
  print("--- Inferring subsets")
  scheme_eval(atomspace, "(pln-load 'empty)")
  scheme_eval(atomspace, "(pln-load-from-path \"rules/patients_subset_rule.scm\")")
  scheme_eval(atomspace, "(pln-add-rule \"gene-expression-subset-rule\")")
  scheme_eval(atomspace, "(pln-add-rule \"patient-data-subset-rule\")")
  target = """
    (Subset 
      (Set (Variable "$p"))
      (Variable "$ppty"))"""

  bc = """
    (pln-bc 
      {}
      #:vardecl (VariableSet 
        (TypedVariable (Variable "$p") (Type "ConceptNode")) 
        (TypedVariable (Variable "$ppty") (Type "SatisfyingSetScopeLink")))
      #:maximum-iterations 2
      #:complexity-penalty 10)
      """.format(target)

  scheme_eval(atomspace, bc) 
  scheme_eval(atomspace, "(pln-load 'empty)")
  scheme_eval(atomspace, "(pln-load-from-path \"rules/patients_subset_rule.scm\")")
  scheme_eval(atomspace, "(pln-add-rule \"patient-data-boolean-subset-rule\")")
  scheme_eval(atomspace, bc) 
  
def apply_subset_rule2(atomspace):
  scheme_eval(atomspace, "(pln-load 'empty)")
  scheme_eval(atomspace, "(pln-load-from-path \"rules/patients-ppty-rule.scm\")")
  scheme_eval(atomspace, "(pln-add-rule \"patient-ppty-subset-rule\")")
  target = """ 
  (Subset 
      (Set (Variable "$p"))
      (SatisfyingSet
          (Variable "$pt")
          (SubsetLink
          (And
              (Variable "$c")
              (ConceptNode "profiled-genes"))
          (SatisfyingSetScopeLink
              (VariableNode "$G")
              (EvaluationLink
              (LazyExecutionOutputLink
                  (Variable "$S")
                  (VariableNode "$G"))
              (Variable "$pt"))))))"""

  bc = """
  (pln-bc 
    {}
    #:maximum-iterations 2
    #:complexity-penalty 10)""".format(target)
  scheme_eval(atomspace, bc)  

def generate_attraction_links(atomspace):
  scheme_eval(atomspace, "(pln-load 'empty)")
  scheme_eval(atomspace, "(pln-load-from-path \"rules/subset_negation_rule.scm\")")
  scheme_eval(atomspace, "(pln-load-from-path \"rules/subset_attraction_rule.scm\")")
  scheme_eval(atomspace, "(pln-add-rule \"subset-negation-patients-rule\")")
  scheme_eval(atomspace, "(pln-add-rule \"subset-attraction-patients-rule\")")
  target = """
  (Subset
  (Not (Set (Variable "$X")))
  (Variable "$Y"))
  """
  target2 = """ 
  (Attraction 
      (Set (Variable "$X")) 
      (Variable "$Y"))
  """
  bc = """
  (pln-bc 
    {}

    #:maximum-iterations 2
    #:complexity-penalty 10)"""
  scheme_eval(atomspace, bc.format(target))
  scheme_eval(atomspace, bc.format(target2))

def calculate_truth_values(atomspace):
  print("--- Calculating Truth Values")

  def get_confidence(count):
    return float(scheme_eval(atomspace, "(count->confidence {})".format(str(count))))

  total_patients = len([x for x in atomspace.get_atoms_by_type(types.ConceptNode) if str(x.name).isnumeric()])
  for s in atomspace.get_atoms_by_type(types.SubsetLink):
    try:
      if s.out[0].type == types.SetLink and s.out[1].type == types.SatisfyingSetScopeLink:
        # set tv of patients as 1 / total number of patients, 
        strength = 1 / total_patients
        confidence = get_confidence(total_patients)
        s.out[0].tv = TruthValue(strength, confidence)

        # get the SatisfyingSetScopeLink and use Get to get the list, devide the number of elements by total no of patients 
        satisf = s.out[1]
        outgoing = " ".join([str(i) for i in satisf.out])
        strength = int(scheme_eval(atomspace, """(length (cog-outgoing-set (cog-execute! (Get {}))))""".format(outgoing))) / total_patients
        confidence = get_confidence(total_patients)
        s.out[1].tv = TruthValue(strength, confidence)
    except Exception as e:
      print(e)
      continue
def remove_processed_subsets(atomspace):
  for e in atomspace.get_atoms_by_type(types.SubsetLink):
    if e.tv.mean == 0 or e.tv.confidence == 0:
      scheme_eval(atomspace,"(cog-delete {})".format(e))

def export_all_atoms(atomspace):
  print("--- Exporting Atoms to files")
  write_atoms_to_file(subset_links_scm, "(cog-get-atoms 'SubsetLink)", atomspace)
  write_atoms_to_file(attraction_links_scm, "(cog-get-atoms 'AttractionLink)", atomspace)

def generate_atoms():
    ### Initialize the AtomSpace ###
    atomspace = AtomSpace()
    initialize_opencog(atomspace)

    ### Guile setup ###
    scheme_eval(atomspace, "(add-to-load-path \".\")")
    scheme_eval(atomspace, """
    (use-modules (opencog) (opencog bioscience) (opencog ure) (opencog logger)
    (opencog pln) (opencog persist-file) (srfi srfi-1) (opencog exec))
    (ure-logger-set-level! "debug")
    """)
    scheme_eval(atomspace, " ".join([
    "(define (write-atoms-to-file file atoms)",
        "(define fp (open-output-file file))",
        "(for-each",
        "(lambda (x) (display x fp))",
        "atoms)",
        "(close-port fp))"]))

    populate_atomspace(atomspace)
    preprocess(atomspace)
    apply_subset_rule1(atomspace)
    apply_subset_rule2(atomspace)
    calculate_truth_values(atomspace)
    remove_processed_subsets(atomspace)
    generate_attraction_links(atomspace)
    export_all_atoms(atomspace)
    return base_results_dir, atomspace

if __name__ == "__main__":
    output_path, kb_as = generate_atoms()
    print("Output path {}".format(output_path))
    generate_embeddings("FMBPV",output_path, kb_atomspace=kb_as)