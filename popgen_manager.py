import MySQLdb
import copy
import cPickle as pickle
import traceback
import sys
import os
import pp

from lxml import etree
from numpy import asarray
from math import floor

from import_data import FileProperties, ImportUserProvData
from configuration.config_parser import ConfigParser
from synthesizer_algorithm.prepare_data import prepare_data
from synthesizer_algorithm.prepare_data_nogqs import prepare_data_nogqs
from synthesizer_algorithm.prepare_data_nogqs_noper import prepare_data_nogqs_noper
from synthesizer_algorithm.prepare_data_noper import prepare_data_noper
from synthesizer_algorithm.drawing_households import person_index_matrix
from synthesizer_algorithm import demo
from synthesizer_algorithm import demo_nogqs
from synthesizer_algorithm import demo_nogqs_noper
from synthesizer_algorithm import demo_noper
from synthesizer_algorithm import demo_parallel
from synthesizer_algorithm import demo_parallel_nogqs
from synthesizer_algorithm import demo_parallel_nogqs_noper
from synthesizer_algorithm import demo_parallel_noper
from newproject import TableNameLoc

from synthesizer_algorithm.export_results import SaveSyntheticPopFile, ExportSummaryFile, ExportMultiwayTables

class ConfigurationError(Exception):
    pass


class PopgenManager(object):
    """
    The class reads the configuration file, creates the component and model objects,
    and runs the models to simulate the various activity-travel choice processes.

    If the configObject is invalid, then a valid fileLoc is desired and if that fails
    as well then an exception is raised. In a commandline implementation, fileLoc will
    be passed.
    """

    def __init__(self, fileLoc=None, configObject =None, parallelFlag=1):
	if fileLoc == None and configObject == None:
	    fileLoc = os.path.realpath('./configuration/config.xml')
	    print 'file location is now assigned to default - ', fileLoc

        if configObject is None and fileLoc is None:
            raise ConfigurationError, """The configuration input is not valid; a """\
                """location of the XML configuration file or a valid etree """\
                """object must be passed"""

        if not ((isinstance(configObject, etree._ElementTree) or isinstance(configObject, etree._Element))
		and configObject is not None):
            print ConfigurationError, """The configuration object input is not a valid """\
                """etree.Element object. Trying to load the object from the configuration"""\
                """ file."""

	self.fileLoc = fileLoc

	if configObject is None:
	    configObject = etree.parse(fileLoc)		
	self.configObject = configObject

	self.parallelFlag = parallelFlag



        print '________________________________________________________________'
        print 'PARSING CONFIG FILE'
        self.configParser = ConfigParser(self.configObject) #creates the model configuration parser
	self.configParser.parse_project()
	self.project = self.configParser.project
	self.create_database()
        print 'COMPLETED PARSING CONFIG FILE AND CREATED THE MASTER DATABASE'
        print '________________________________________________________________'

	try:
	    os.mkdir('%s%s%s' %(self.project.location, os.path.sep, self.project.name))
	except Exception, e:
	    print ('Warning when creating folder:', e)



        ppservers = ()
        self.job_server = pp.Server(ppservers=ppservers, restart = True)



    def create_database(self):
	if self.project.createTables:
	    self.drop_main_database()
	    self.setup_database()
            self.create_tables()



    def setup_database(self, name=None):
	#Create Database
	db = MySQLdb.connect(user= '%s' %self.project.db.username,
                             passwd = '%s' %self.project.db.password, local_infile=1)
	dbc = db.cursor()
	
	if name is None:
	    dbName = self.project.name
	else:
	    dbName = name

	try:
	    dbc.execute("Create Database if not exists %s" %(dbName))
	except Exception, e:
	    print '\tError occurred when creating database:%s' %e
	dbc.close()


    def drop_main_database(self):
	db = MySQLdb.connect(user= '%s' %self.project.db.username,
                             passwd = '%s' %self.project.db.password, local_infile=1)
	dbc = db.cursor()
	
	dbList = [self.project.name]
	
	for dbName in dbList:
	    try:
	        dbc.execute("Drop Database if exists %s" %(dbName))
 	    except Exception, e:
	        print '\tError occurred when dropping database:%s' %e

	#raw_input('--Completed deleting all databases--')
	
    def drop_scenario_database(self):
	db = MySQLdb.connect(user= '%s' %self.project.db.username,
                             passwd = '%s' %self.project.db.password, local_infile=1)
	dbc = db.cursor()
	
	dbList = []
	for scenario in self.scenarioList:
            if scenario.prepareData:
	        dbList.append('%s%s%s' %(scenario.name, 'scenario', scenario.scenario))
	
	for dbName in dbList:
	    try:
	        dbc.execute("Drop Database if exists %s" %(dbName))
 	    except Exception, e:
	        print '\tError occurred when dropping database:%s' %e


    def create_tables(self):
	print '-- Creating tables -- '
	# Connect to the actual project database
        db = MySQLdb.connect(user = '%s' %self.project.db.username,
                             passwd = '%s' %self.project.db.password,
                             db = '%s' %(self.project.name), local_infile=1)


	#Create Geographic Correspondence Table
	geoCorrFileQuery = self.mysql_queries('geocorr', 
					      self.project.geocorrUserProv.location)
	self.execute_queries(db, geoCorrFileQuery)
	self.add_legacy_columns('geocorr', geocorr=True)
        #self.add_index(db, 'geocorr', ['taz'])

	#Create Sample Tables
	hhldSampleQuery = self.mysql_queries('hhld_sample',
					     self.project.sampleUserProv.hhLocation)
	self.execute_queries(db, hhldSampleQuery)
	self.add_legacy_columns('hhld_sample', sample=True)
	self.add_index(db, 'hhld_sample', ['state', 'serialno'])

	if self.project.sampleUserProv.gqLocation <> "":
	    gqSampleQuery = self.mysql_queries('gq_sample',
		                               self.project.sampleUserProv.gqLocation)
            self.execute_queries(db, gqSampleQuery)
	    self.add_legacy_columns('gq_sample', sample=True)
	    self.add_index(db, 'gq_sample', ['state', 'serialno'])

	personSampleQuery = self.mysql_queries('person_sample',
					   self.project.sampleUserProv.personLocation)
	self.execute_queries(db, personSampleQuery)
	self.add_legacy_columns('person_sample', sample=True)
	self.add_index(db, 'person_sample', ['state', 'serialno','pnum'])
	#Create Marginal Tables

	hhldMarginalQuery = self.mysql_queries('hhld_marginals',
					       self.project.controlUserProv.hhLocation)
	self.execute_queries(db, hhldMarginalQuery)
	self.add_legacy_columns('hhld_marginals', marginals=True)
        self.add_old_geo_id_columns('hhld_marginals')

	if self.project.controlUserProv.gqLocation:
	    gqMarginalQuery = self.mysql_queries('gq_marginals',
					         self.project.controlUserProv.gqLocation)
	    self.execute_queries(db, gqMarginalQuery)
	    self.add_legacy_columns('gq_marginals', marginals=True)
            self.add_old_geo_id_columns('gq_marginals')

	personMarginalQuery = self.mysql_queries('person_marginals',
					         self.project.controlUserProv.personLocation)
	self.execute_queries(db, personMarginalQuery)
	self.add_legacy_columns('person_marginals', marginals=True)
        self.add_old_geo_id_columns('person_marginals')


    def add_old_geo_id_columns(self, tableName):
        db = MySQLdb.connect(user = '%s' %self.project.db.username,
                             passwd = '%s' %self.project.db.password,
                             db = '%s' %(self.project.name), local_infile=1)
	dbc = db.cursor()
        try:
            print ("""create table %s_temp select geocorr.state, geocorr.county, """\
                       """%s.* from geocorr, %s where %s.taz = geocorr.taz""" \
                       %(tableName, tableName, tableName, tableName))
            
            dbc.execute("""create table %s_temp select geocorr.state, geocorr.county, """\
                            """%s.* from geocorr, %s where %s.taz = geocorr.taz""" \
                            %(tableName, tableName, tableName, tableName))

            dbc.execute("""drop table %s""" %tableName)
            dbc.execute("""rename table %s_temp to %s """ %(tableName, tableName))
                        
        except Exception, e:
            print '\t Error occurred when adding legacy columns to %s: %s' %(tableName, e)

	dbc.close()
	db.commit()

    def add_legacy_columns(self, tableName, sample=False, marginals=False, geocorr=False):
        db = MySQLdb.connect(user = '%s' %self.project.db.username,
                             passwd = '%s' %self.project.db.password,
                             db = '%s' %(self.project.name), local_infile=1)
	dbc = db.cursor()
	if sample:
	    try:
		dbc.execute('alter table %s add column serialno bigint after hhid' %tableName)
	    except Exception, e:
	        print '\tError occurred when adding legacy columns to %s: %s' % (tableName, e)
	
	    try:
		dbc.execute('update %s set serialno = hhid' %tableName)
	    except Exception, e:
	        print '\tError occurred when adding legacy columns to %s: %s' % (tableName, e)

	if marginals or geocorr:
	    try:
		dbc.execute('alter table %s add column tract bigint after taz' %tableName)
	    except Exception, e:
	        print '\tError occurred when adding legacy columns to %s: %s' % (tableName, e)

	    try:
		dbc.execute('alter table %s add column bg bigint after tract' %tableName)
	    except Exception, e:
	        print '\tError occurred when adding legacy columns to %s: %s' % (tableName, e)



	    try:
		dbc.execute('update %s set tract = 1' %tableName)
	    except Exception, e:
	        print '\tError occurred when adding legacy columns to %s: %s' % (tableName, e)
		
	    try:
		dbc.execute('update %s set bg = taz' %tableName)
	    except Exception, e:
	        print '\tError occurred when adding legacy columns to %s: %s' % (tableName, e)

	dbc.close()
	db.commit()



    def mysql_queries(self, name, filePath):
        fileProp = FileProperties(filePath)
        fileQuery = ImportUserProvData(name,
                                       filePath,
                                       fileProp.varNames,
                                       fileProp.varTypes,
                                       fileProp.varNamesDummy,
                                       fileProp.varTypesDummy)
	#print fileQuery.query1, fileQuery.query2
        return fileQuery

    def execute_queries(self, db, query):
	dbc = db.cursor()
	try:
	    dbc.execute(query.query1)
	except Exception, e:
	    print '\tError occurred when creating table definition: %s' %e
	try:
	    dbc.execute(query.query2)
	except Exception, e:
	    print '\tError occurred when populating the table: %s' %e
	dbc.close()
	db.commit()


    def add_index(self, db, tableName, indexVarList):
	indexVarStr = ""
	for var in indexVarList:
	    indexVarStr += "%s," %var
	indexVarStr = indexVarStr[:-1]
	dbc = db.cursor()
	try:
	    dbc.execute("""alter table %s add index(%s)"""
			%(tableName, indexVarStr))
	except Exception, e:
	    print '\tError occurred when adding index to the table: %s' %e

    def prepare_data(self, scenario, state=None):
        self.remove_tables(scenario)

        if scenario.selVariableDicts.hhldMargsModify:
            self.modify_marginals(scenario)
        
        db = MySQLdb.connect(user = '%s' %self.project.db.username,
                             passwd = '%s' %self.project.db.password,
                             db = '%s%s%s' %(scenario.name, 'scenario', scenario.scenario), local_infile=1)

        try:
            if self.gqAnalyzed and scenario.selVariableDicts.persControl:
		print 'PERSON AND GQ CONTROLLED'
                prepare_data(db, scenario, state=state)
            if self.gqAnalyzed and not scenario.selVariableDicts.persControl:
		print 'NO PERSON and GQ CONTROLELD'
                prepare_data_noper(db, scenario, state=state)
            if not self.gqAnalyzed and scenario.selVariableDicts.persControl:
		print 'PERSON AND NO GQ'
                prepare_data_nogqs(db, scenario, state=state)
            if not self.gqAnalyzed and not scenario.selVariableDicts.persControl:
		print 'NO PERSON AND NO GQ'
                prepare_data_nogqs_noper(db, scenario, state=state)
        except KeyError, e:
            print ("""Check the <b>hhid, serialno</b> columns in the """\
                   """data. If you wish not to synthesize groupquarters, make"""\
                   """ sure that you delete all person records corresponding """\
                   """to groupquarters. In PopGen, when Census data is used, """\
                   """by default groupquarters need"""\
                   """ to be synthesized because person marginals include """\
                   """individuals living in households and groupquarters. Fix the data"""\
                   """ and run synthesizer again.""")
            
        db.commit()
                             
    def remove_tables(self, scenario):
	dbName = '%s%s%s' %(scenario.name, 'scenario', scenario.scenario)

        self.setup_database(dbName)

	try:
	    db = MySQLdb.connect(user = '%s' %self.project.db.username,
                                 passwd = '%s' %self.project.db.password,
                                 db = dbName, local_infile=1)
	    dbc = db.cursor()
            dbc.execute("""Drop table if exists hhld_sample""")
            dbc.execute("""Drop table if exists person_sample""")
            dbc.execute("""Drop table if exists gq_sample""")
            dbc.execute("""Drop table if exists hhld_marginals""")
            dbc.execute("""Drop table if exists person_marginals""")
            dbc.execute("""Drop table if exists gq_marginals""")
	    dbc.close()
	    db.commit()
	except Exception, e:
	    print '\tError occurred when dropping the database: %s' %e
	#raw_input('--Completed deleting input tables from the scenario database--')

    def populate_full_input_tables(self, scenario):
	scenarioDatabase = '%s%s%s' %(scenario.name, 'scenario', scenario.scenario)
	projectDatabase = self.project.name
	
	try:
	    db = MySQLdb.connect(user = '%s' %self.project.db.username,
                                 passwd = '%s' %self.project.db.password,
                                 db = scenarioDatabase, local_infile=1)

	    dbc = db.cursor()

    	    dbc.execute('create table %s.hhld_sample select * from %s.hhld_sample '%(scenarioDatabase, projectDatabase))
	    self.add_index(db, 'hhld_sample', ['state', 'serialno'])


	    dbc.execute('create table %s.person_sample select * from %s.person_sample'%(scenarioDatabase, projectDatabase))
	    self.add_index(db, 'person_sample', ['state', 'serialno', 'pnum'])


    	    if scenario.selVariableDicts.hhldMargsModify:
        	dbc.execute('create table %s.hhld_marginals select * from %s.hhld_marginals_modpgq'
                    	     %(scenarioDatabase, projectDatabase))
    	    else:
        	dbc.execute('create table %s.hhld_marginals select * from %s.hhld_marginals'
                    	     %(scenarioDatabase, projectDatabase))

    	    dbc.execute('create table %s.person_marginals select * from %s.person_marginals'
                	 %(scenarioDatabase, projectDatabase))


            if self.gqAnalyzed:
	        dbc.execute('create table %s.gq_sample select * from %s.gq_sample' %(scenarioDatabase, projectDatabase))
 	        self.add_index(db, 'gq_sample', ['state', 'serialno'])

    	    	dbc.execute('create table %s.gq_marginals select * from %s.gq_marginals'
                	     %(scenarioDatabase, projectDatabase))

	    dbc.close()
	    db.commit()
	except Exception, e:
	    print '\tError occurred when dropping the database: %s' %e
	#raw_input('--Completed importing full inputs across all states --')

    def modify_marginals(self, scenario):
        # Calculating the Person Total
        refPersName = scenario.selVariableDicts.refPersName
        varsT = scenario.selVariableDicts.person['%s' %refPersName].values()
        self.add_total_column(varsT, 'person_marginals', 'persontotal')

        # Calculating the groupquarter Total
        if self.gqAnalyzed:
            refGQName = scenario.selVariableDicts.gq.keys()[0]
            varsT = scenario.selVariableDicts.gq['%s' %refGQName].values()
            self.add_total_column(varsT, 'gq_marginals', 'gqtotal')

        # Calculating the household total
        refHhldName = scenario.selVariableDicts.hhldSizeVarName
        varsT = scenario.selVariableDicts.hhld['%s' %refHhldName].values()

        self.add_total_column(varsT, 'hhld_marginals', 'hhldtotal')

        # Create the new modified hhld marginals table
        self.create_mod_hhld_table()

        # Create hhld variable proportions
        self.create_hhld_var_proportions(scenario)

        
        # Create the number of deficient households
        self.calc_extra_hhlds_to_syn(scenario)

        self.calc_modified_marginals(scenario)


    def add_total_column(self, varsTot, tablename, varname):
        varString = ''
        for i in varsTot:
            varString = varString + i + '+'
        varString = varString[:-1]

        db = MySQLdb.connect(user = '%s' %self.project.db.username,
                             passwd = '%s' %self.project.db.password,
                             db = '%s' %self.project.name, local_infile=1)
        dbc = db.cursor()

        try:
            dbc.execute("alter table %s add index(state, county, tract, bg)" %tablename)
        except Exception, e:
            print '\tError occurred when adding index: %s' %e

        try:
            dbc.execute("alter table %s add column %s bigint" %(tablename, varname))
        except Exception, e:
            print '\tError occurred when adding column: %s' %e

        try:
            dbc.execute("update %s set %s = %s" %(tablename, varname, varString))
        except Exception, e:
            print '\tError occurred when updating the total column: %s' %e

        dbc.close()
        db.commit()

    def create_mod_hhld_table(self):
        db = MySQLdb.connect(user = '%s' %self.project.db.username,
                             passwd = '%s' %self.project.db.password,
                             db = '%s' %self.project.name, local_infile=1)
        dbc = db.cursor()


        try:
            dbc.execute("drop table if exists hhld_marginals_modp")
        except Exception, e:
            print '\tError occurred when dropping modified household marginals table: %s' %e

        try:
            dbc.execute("drop table if exists hhld_marginals_modpgq")
        except Exception, e:
            print '\tError occurred when dropping modified household marginals table with person vars: %s' %e


        try:
            dbc.execute("""create table hhld_marginals_modp select hhld_marginals.*, persontotal from hhld_marginals"""
                           """ left join person_marginals using(state, county, tract, bg)""")
        except Exception, e:
            print '\tError occurred when creating modified household marginals table: %s' %e

        if self.gqAnalyzed:
            try:
                dbc.execute("""create table hhld_marginals_modpgq select hhld_marginals_modp.*, """\
                                """gqtotal from hhld_marginals_modp"""
                               """ left join gq_marginals using(state, county, tract, bg)""")
            except Exception, e:
                print '\tError occurred when appending modified household marginals table with person vars: %s' %e
        else:
            try:
                dbc.execute("""create table hhld_marginals_modpgq select * from hhld_marginals_modp""")
            except Exception, e:
                print '\tError occurred when creatring modified marginals table with person vars: %s' %e

            try:
                dbc.execute("""alter table hhld_marginals_modpgq add column gqtotal bigint default 0""")
            except Exception, e:
                print '\tError occurred when adding a dummy gq total column: %s' %e

        dbc.close()
        db.commit()


    def create_hhld_var_proportions(self, scenario):
        db = MySQLdb.connect(user = '%s' %self.project.db.username,
                             passwd = '%s' %self.project.db.password,
                             db = '%s' %self.project.name, local_infile=1)
        dbc = db.cursor()


        try:
            dbc.execute
        except Exception, e:
            print '\tError occurred when adding index: %s' %e

        #calculating the proportions
        for i in scenario.selVariableDicts.hhld.keys():
            sumString = ''
            for j in scenario.selVariableDicts.hhld[i].values():
                sumString = sumString + j + '+'
            sumString = sumString[:-1]

            for j in scenario.selVariableDicts.hhld[i].values():
                try:
                    dbc.execute("""alter table hhld_marginals_modpgq add column p%s float(27)""" %j)
                except Exception, e:
                    print '\tError occurred when adding column for proportions: %s' %e

                try:
                    dbc.execute("""update hhld_marginals_modpgq set p%s = %s/(%s)""" %(j, j, sumString))
                except Exception, e:
                    print '\tError occurred when adding column for proportions: %s' %e

        dbc.close()
        db.commit()



    def calc_extra_hhlds_to_syn(self, scenario):
        db = MySQLdb.connect(user = '%s' %self.project.db.username,
                             passwd = '%s' %self.project.db.password,
                             db = '%s' %self.project.name, local_infile=1)
        dbc = db.cursor()


        # Calculating the number of extra households to be synthesizsed
        # PEQP = Person Equivalent Proportions
        # PEQ = Person Equivalents
        # PSUM = Proportions Sum

        hhldsizeVarName = scenario.selVariableDicts.hhldSizeVarName
        varsT = scenario.selVariableDicts.hhld['%s' %hhldsizeVarName].values()
        varsT.sort()

        hhldsizePEQPString = ''
        hhldsizePEQString = ''
        hhldsizePSumString = ''

        size = 1

        for i in varsT[:-1]:
            hhldsizePEQPString = hhldsizePEQPString + 'p' + i + '*%s+' %size
            hhldsizePEQString = hhldsizePEQString + i + '*%s+' %size
            hhldsizePSumString = hhldsizePSumString + 'p' + i + '+'
            size = size + 1

        hhldsizePEQPString = hhldsizePEQPString[:-1]
        hhldSize = scenario.selVariableDicts.aveHhldSizeLastCat
        hhldsizePEQString = hhldsizePEQString + varsT[-1]+'*%s' %hhldSize

        # this is a makeshift change to modify the marginals distributions
        print hhldsizePEQPString
        hhldsizePEQPString = hhldsizePEQPString + '+ p' + varsT[-1] +'*%s' %hhldSize
        print hhldsizePEQPString

        hhldsizePSumString = hhldsizePSumString[:-1]

        # Creating person equivalents column
        try:
            dbc.execute("""alter table hhld_marginals_modpgq add column perseq bigint""")
        except Exception, e:
            print '\tError occurred when creating person equivalents column: %s' %e

        try:
            dbc.execute("""update hhld_marginals_modpgq set perseq = %s + gqtotal""" %(hhldsizePEQString))
        except Exception, e:
            print '\tError occurred when updating person equivalents column: %s' %e


        # Creating person total deficiency
        try:
            dbc.execute("""alter table hhld_marginals_modpgq add column perstotdef bigint""")
        except Exception, e:
            print '\tError occurred when adding person total deficiency column: %s' %e

        try:
            dbc.execute("""update hhld_marginals_modpgq set perstotdef = persontotal - perseq""")
        except Exception, e:
            print '\tError occurred when updating person total deficiency column: %s' %e


        # Creating the number of deficient household equivalents
        try:
            dbc.execute("""alter table hhld_marginals_modpgq add column hhldeqdef float(27)""")
        except Exception, e:
            print '\tError occurred when creating deficient household equivalents column: %s' %e


        try:
            dbc.execute("""update hhld_marginals_modpgq set hhldeqdef = perstotdef/(%s)""" %hhldsizePEQPString)
        except Exception, e:
            print '\tError occurred when updating deficient household equivalents column: %s' %e

        dbc.close()
        db.commit()


    def calc_modified_marginals(self, scenario):
        db = MySQLdb.connect(user = '%s' %self.project.db.username,
                             passwd = '%s' %self.project.db.password,
                             db = '%s' %self.project.name, local_infile=1)
        dbc = db.cursor()

        #calculating the proportions
        hhldsizeVar = scenario.selVariableDicts.hhldSizeVarName
        hhldSizeCats = scenario.selVariableDicts.hhld['%s'%hhldsizeVar].keys()
        numCats = len(hhldSizeCats)

        lastCatKey = hhldsizeVar + ', Category %s'%numCats
        lastCatMarg = scenario.selVariableDicts.hhld['%s'%hhldsizeVar]['%s'%lastCatKey]

        for i in scenario.selVariableDicts.hhld.keys():
            sumString = ''
            for j in scenario.selVariableDicts.hhld[i].values():
                sumString = sumString + j + '+'
            sumString = sumString[:-1]

            for j in scenario.selVariableDicts.hhld[i].values():
                try:
                    dbc.execute("""alter table hhld_marginals_modpgq add column mod%s float(27)""" %j)
                except Exception, e:
                    print '\tError occurred when creating column for modified marginals: %s' %e
                
                try:
                    dbc.execute("""update hhld_marginals_modpgq set mod%s = %s + p%s * hhldeqdef""" %(j, j, j))
                except Exception, e:
                    print '\tError occurred when updating column for modified marginals: %s' %e

        dbc.close()
        db.commit()


    def is_gq_analyzed(self, scenario):
        if not scenario.gqVars:
            return False

        if scenario.sampleUserProv.userProv == True and scenario.sampleUserProv.gqLocation <> "":
            return True

        if scenario.controlUserProv.userProv == True and scenario.controlUserProv.gqLocation <> "":
            return True

        return False

    def read_data(self, scenario):
        db = MySQLdb.connect(user = '%s' %self.project.db.username,
                             passwd = '%s' %self.project.db.password,
                             db = '%s%s%s' %(scenario.name, 'scenario', scenario.scenario), local_infile=1)
        dbc = db.cursor()

        dbc.execute("""select * from index_matrix_%s""" %(99999))
        indexMatrix = asarray(dbc.fetchall())

        f = open('%s%s%s%sindexMatrix_99999.pkl' %(self.project.location, os.path.sep,
						   self.project.name, os.path.sep), 'wb')
        pickle.dump(indexMatrix, f)
        f.close()

        pIndexMatrix = person_index_matrix(db)
        f = open('%s%s%s%spIndexMatrix.pkl' %(self.project.location, os.path.sep,
					      self.project.name, os.path.sep), 'wb')
        pickle.dump(pIndexMatrix, f)
        f.close()

        dbc.close()
        db.close()

    def delete_records_for_geographies(self, scenario, state=None):
	dbName = '%s%s%s' %(scenario.name, 'scenario', scenario.scenario)
        db = MySQLdb.connect(user = '%s' %self.project.db.username,
                             passwd = '%s' %self.project.db.password,
                             db = dbName, local_infile=1)
        dbc = db.cursor()

        if state == None:
            stateFilterStr = ""
        else:
            stateFilterStr = state

	for geo in scenario.synthesizeGeoIds:
	    if geo.state <> state:
		continue
	    try:
	        dbc.execute("""delete from %s.housing_synthetic_data where state = %s and county = %s """
                                       """ and tract = %s and bg = %s  """ %(dbName, stateFilterStr, geo.county,
									     geo.tract, geo.bg))
	    except Exception, e:
	        print '\tError occurred when deleting housing records: %s' %e


	    try:
	        dbc.execute("""delete from %s.person_synthetic_data where state = %s and county = %s """
                                       """ and tract = %s and bg = %s  """ %(dbName, geo.state, geo.county,
									     geo.tract, geo.bg))
	    except Exception, e:
	        print '\tError occurred when deleting person records: %s' %e

        dbc.close()
        db.close()

    def variable_control_corr_dict(self, vardict):
        varCorrDict = {}
        varsT = vardict.keys()
        for i in varsT:
            for j in vardict[i].keys():
                cat = (('%s' %j).split())[-1]
                varCorrDict['%s%s' %(i, cat)] = '%s' %vardict[i][j]
        return varCorrDict


    def synthesize_population(self, scenario, state=None):

	if self.parallelFlag == "0":
	    print ("Running the synthesizer in serial")	
            self.run_synthesizer_in_serial(scenario, state)
        elif self.job_server.get_ncpus() > 1:
            print ("There are multiple cores - %s, running the synthesizer in parallel" %self.job_server.get_ncpus())
            self.run_synthesizer_in_parallel(scenario, state)
        else:
            print ("There are no multiple cores - %s running the synthesizer in serial" %self.job_server.get_ncpus())	
            self.run_synthesizer_in_serial(scenario, state)

    def run_synthesizer_in_parallel(self, scenario, state=None):
        varCorrDict = {}

        hhldDict = copy.deepcopy(scenario.selVariableDicts.hhld)
        if scenario.selVariableDicts.hhldMargsModify:
            for i in hhldDict.keys():
                for j in hhldDict[i].keys():
                    hhldDict[i][j] = 'mod' + hhldDict[i][j]

        varCorrDict.update(self.variable_control_corr_dict(hhldDict))
        if self.gqAnalyzed:
            varCorrDict.update(self.variable_control_corr_dict(scenario.selVariableDicts.gq))
        varCorrDict.update(self.variable_control_corr_dict(scenario.selVariableDicts.person))

	# Run the first synthesis in serial to make sure all the tables/data structures
	# are created correctly

        print 'Total number of geographies', len(scenario.synthesizeGeoIds)
        #raw_input()
	
	stateGeos = []
	
	for geo in scenario.synthesizeGeoIds:
	    geo = self.getPUMA5(geo)
	    if geo.state == state:
	    	stateGeos.append(geo)

        # Sort by PUMA ID's for parallelizing
        geoPUMADict = {}
        for geo in stateGeos:
            #print geoPUMADict.keys(), geo.puma5
            #raw_input('break here')
            if geo.puma5 in geoPUMADict.keys():
                #print geo.puma5, type(geo.puma5)
                #print geoPUMADict[geo.puma5]
                geoPUMADict[geo.puma5].append(geo)
            else:
                geoPUMADict[geo.puma5] = [geo]

        for puma in geoPUMADict.keys():
            geoList = geoPUMADict[puma]

            print 'Running synthesizer in parallel for PUMA - %s and number of geos for this is - %d' %(puma, len(geoList))
            #raw_input('Press any key to continue --- ')
            self.run_synthesizer_in_parallel_for_geoList(scenario, geoList, varCorrDict)
            #raw_input('Processing complete for PUMA press any key to continue --- ')

    def run_synthesizer_in_parallel_for_geoList(self, scenario, geoList, varCorrDict):

	
	geo = geoList[0]
	print geo
	try:
	    
	    if self.gqAnalyzed and scenario.selVariableDicts.persControl:
		print '  - GQ ANALYZED WITH PERSON ATTRIBUTES CONTROLLED'
		demo.configure_and_run(scenario, geo, varCorrDict)
	    if self.gqAnalyzed and not scenario.selVariableDicts.persControl:
		print '  - GQ ANALYZED WITH NO PERSON ATTRIBUTES CONTROLLED'
		demo_noper.configure_and_run(scenario, geo, varCorrDict)
	    if not self.gqAnalyzed and scenario.selVariableDicts.persControl:
		print '  - NO GQ ANALYZED WITH PERSON ATTRIBUTES CONTROLLED'
		demo_nogqs.configure_and_run(scenario, geo, varCorrDict)
	    if not self.gqAnalyzed and not scenario.selVariableDicts.persControl:
		print '  - NO GQ ANALYZED WITH NO PERSON ATTRIBUTES CONTROLLED'
		demo_nogqs_noper.configure_and_run(scenario, geo, varCorrDict)
            
	    runGeoIds = []
	    for geo in geoList[1:]:
	    	runGeoIds.append((geo.state, geo.county, geo.puma5, geo.tract, geo.bg))
            geoCount = len(runGeoIds)
            binsize = 50

            bins = int(floor(geoCount/binsize))
	    index = [((i+1)*binsize, (i+1)*binsize+binsize) for i in range(bins-1)]
                
            if bins > 0:
                index.append((0, binsize))
            	index.append((bins*binsize, geoCount))

            else:
                if geoCount > 1:
                    index.append((0, geoCount))

	    print 'len of geoList - ', len(geoList)
	    print 'len of runGeoIds - ', len(runGeoIds)
	    for i in index:
	    	print '\t individual batch len - %s and anchors are %s and %s' %(len (runGeoIds[i[0]:i[1]]),
	    									  i[0],
	    									  i[1])
        	for g in runGeoIds[i[0]:i[1]]:
        	    print g
        	
        	if self.gqAnalyzed and scenario.selVariableDicts.persControl:
                    #print 'GQ ANALYZED WITH PERSON ATTRIBUTES CONTROLLED'
                    demo_parallel.run_parallel(self.job_server, scenario, runGeoIds[i[0]:i[1]], 
                    				varCorrDict, coreVersion=True)
                if self.gqAnalyzed and not scenario.selVariableDicts.persControl:
                    #print 'GQ ANALYZED WITH NO PERSON ATTRIBUTES CONTROLLED'
                    demo_parallel_noper.run_parallel(self.job_server, scenario, runGeoIds[i[0]:i[1]], 
                    					varCorrDict, coreVersion=True)
                if not self.gqAnalyzed and scenario.selVariableDicts.persControl:
                    #print 'NO GQ ANALYZED WITH PERSON ATTRIBUTES CONTROLLED'
                    demo_parallel_nogqs.run_parallel(self.job_server, scenario, runGeoIds[i[0]:i[1]], 
                    					varCorrDict, coreVersion=True)
                if not self.gqAnalyzed and not scenario.selVariableDicts.persControl:
                     #print 'NO GQ ANALYZED WITH NO PERSON ATTRIBUTES CONTROLLED'
                     demo_parallel_nogqs_noper.run_parallel(self.job_server, scenario, runGeoIds[i[0]:i[1]], 
                     						varCorrDict, coreVersion=True)
		
	    	#raw_input("waiting")
	except Exception, e:
	    print ("\tError in the Synthesis for geography: %s" %e)
            traceback.print_exc(file=sys.stdout)
	    	

    def run_synthesizer_in_serial(self, scenario, state=None):
        varCorrDict = {}

        hhldDict = copy.deepcopy(scenario.selVariableDicts.hhld)
        if scenario.selVariableDicts.hhldMargsModify:
            for i in hhldDict.keys():
                for j in hhldDict[i].keys():
                    hhldDict[i][j] = 'mod' + hhldDict[i][j]

        varCorrDict.update(self.variable_control_corr_dict(hhldDict))
        if self.gqAnalyzed:
            varCorrDict.update(self.variable_control_corr_dict(scenario.selVariableDicts.gq))
        varCorrDict.update(self.variable_control_corr_dict(scenario.selVariableDicts.person))

	for geo in scenario.synthesizeGeoIds:
	    #print ("Running Syntheiss for geography State - %s, County - %s, Tract - %s, BG - %s"
            #       %(geo.state, geo.county, geo.tract, geo.bg))
	    geo = self.getPUMA5(geo)
            print '\t State for geography - %s and state synthesized - %s' %(geo.state, state)

            if geo.state <> state:
                continue
            else:
                try:
                    if self.gqAnalyzed and scenario.selVariableDicts.persControl:
                        print '  - GQ ANALYZED WITH PERSON ATTRIBUTES CONTROLLED'
                        demo.configure_and_run(scenario, geo, varCorrDict)
                    if self.gqAnalyzed and not scenario.selVariableDicts.persControl:
                        print '  - GQ ANALYZED WITH NO PERSON ATTRIBUTES CONTROLLED'
                        demo_noper.configure_and_run(scenario, geo, varCorrDict)
                    if not self.gqAnalyzed and scenario.selVariableDicts.persControl:
                        print '  - NO GQ ANALYZED WITH PERSON ATTRIBUTES CONTROLLED'
                        demo_nogqs.configure_and_run(scenario, geo, varCorrDict)
                    if not self.gqAnalyzed and not scenario.selVariableDicts.persControl:
                        print '  - NO GQ ANALYZED WITH NO PERSON ATTRIBUTES CONTROLLED'
                        demo_nogqs_noper.configure_and_run(scenario, geo, varCorrDict)
                except Exception, e:
                    print ("\tError in the Synthesis for geography: %s" %e)
                    traceback.print_exc(file=sys.stdout)

    def getPUMA5(self, geo):
        db = MySQLdb.connect(user = '%s' %self.project.db.username,
                             passwd = '%s' %self.project.db.password,
                             db = self.project.name, local_infile=1)
        dbc = db.cursor()

        if geo.puma5 is None:
	    try:
                dbc.execute("""select pumano from geocorr where state = %s and county = %s and tract = %s and bg = %s"""
                                   %(geo.state, geo.county, geo.tract, geo.bg))
		results = asarray(dbc.fetchall())
  	        geo.puma5 = results[0][0]
		#print geo
            except Exception, e:
	       print ("\tError occurred when identifying the puma number for the geography: %s" %e)

        dbc.close()
        db.close()
        return geo

    def export_results(self, scenario):
        print '\nExporting results for use in the BMC TDM...'
      
        print '\t\tExporting disaggregate synthetic population results ... --'
	if scenario.synTableExport:
            popFileDlg = SaveSyntheticPopFile(scenario, scenario.synPersTableNameLoc, scenario.synHousingTableNameLoc)
	    popFileDlg.save()


        print '\t\tExporting summary results ... --'
	if scenario.summaryTableExport:
            summaryFileDlg = ExportSummaryFile(scenario, scenario.summaryTableNameLoc)
	    summaryFileDlg.save()
      
     
	if len(scenario.multiwayTableList) > 0:
            print '\t\tExporting multiway table results ... --'
            print '\t\t\tCreating the synthetic files with variables appended'
            defHousingLoc = '%s%s%s' %(self.project.location, os.path.sep,
				       self.project.name)
            defPersonLoc = '%s%s%s' %(self.project.location, os.path.sep,
				      self.project.name)
	
	    defHousingTableNameLoc = TableNameLoc('housing_synthetic', defHousingLoc)
	    defPersonTableNameLoc = TableNameLoc('person_synthetic', defPersonLoc)	
            popFileDlg = SaveSyntheticPopFile(scenario, defHousingTableNameLoc, defPersonTableNameLoc)
            popFileDlg.save()

	    for mwayTable in scenario.multiwayTableList:
            	mwayFileDlg = ExportMultiwayTables(scenario, mwayTable)
		mwayFileDlg.saveMultiwayTables()
	


    def run_scenarios(self):
        skipFlag = self.configParser.parse_skip()
        
        if skipFlag:
            print 'Skipping PopGen run ---'
            return

	self.configParser.parse_scenarios()
	self.scenarioList = self.configParser.scenarioList
        self.stateList = self.configParser.stateList

        self.drop_scenario_database()        
	for scenario in self.scenarioList:
            if len(self.stateList) > 1:
                print 'Synthesis for multiple states is required'
	    self.gqAnalyzed = self.is_gq_analyzed(scenario)        
            
            for state in self.stateList:
                print '\t\tGeoIds for state - ', state


                print '________________________________________________________________'
                if len(scenario.synthesizeGeoIds) == 0:
                    print 'No geographies to synthesize for scenario with description - %s and state - %s' %(scenario.description,
                                                                                                             state)
                    continue
                
                if not scenario.run:
                    continue
                print 'Running Synthesis for Project - %s and Scenario - %s' %(scenario.name, scenario.scenario)
                print '  - Description for Scenario: %s' %(scenario.description)
                if scenario.prepareData:
                    self.prepare_data(scenario, state=state)
                self.delete_records_for_geographies(scenario, state=state)
                self.read_data(scenario)
                self.synthesize_population(scenario, state=state)
            
	    self.remove_tables(scenario)
	    self.populate_full_input_tables(scenario)
            self.export_results(scenario)
	    
if __name__ == '__main__':
    p = PopgenManager()
    p.run_scenarios()


