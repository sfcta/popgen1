import getopt, sys

from configuration.config_parser import ConfigParser
from popgen_manager import PopgenManager


USAGE = """

 python popgen_run.py [-e] config.xml [0]

 The first argument is the location of the configuration file.

 The second argument is an indicator for running in
 serial or parallel and is optional; 0 indicates run in serial.
 Otherwise parallel operation on multiple cores are assumed (if
 multiple cores are available).
 
 Optional -e is for export-results only (do not run).
 
 e.g. /home/config.xml (linux machine single core)
     c:/testproject/config.xml (windows machine single core)
 e.g. /home/config.xml 1(linux machine run in parallel)
     or c:/testproject/config.xml 1(windows machine run in parallel)
    
"""

def run():
    """
    Runs the OpenAMOS program to simulate the activity-travel choices as 
    indicated by the models and their specifications in the config file.

    Please refer to OpenAMOS documentation on www.simtravel.wikispaces.asu.edu
    for guidance on setting up the configuration file.
    """
    
    optlist, args = getopt.getopt(sys.argv[1:],'e')

    print args

    if len(args) < 1 or len(args) > 2:
        raise ArgumentsError, USAGE

    if len(args) == 2:
        pFlag = args[1]
    else:
    	pFlag = 1
    
    export_results_only = False
    for o,a in optlist:
        if o=='-e':
            print "Exporting results only"
            export_results_only = True
    
    popgenManagerObject = PopgenManager(fileLoc = args[0], parallelFlag=pFlag)
    popgenManagerObject.run_scenarios(export_results_only)



if __name__ == "__main__":
    sys.exit(run())
