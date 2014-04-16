# PopGen 1.1 is A Synthetic Population Generator for Advanced
# Microsimulation Models of Travel Demand
# Copyright (C) 2009, Arizona State University
# See PopGen/License

# Running IPF on Person and Household data

import synthesizer_algorithm.heuristic_algorithm_nogqs_noper
import synthesizer_algorithm.psuedo_sparse_matrix
import synthesizer_algorithm.drawing_households
import synthesizer_algorithm.adjusting_sample_joint_distribution
import synthesizer_algorithm.ipf_nosql
from newproject import Geography
import scipy
import scipy.stats
import numpy
import MySQLdb
import time
import sys
import pp
import pickle
import os

def configure_and_run(fileLoc, geo, varCorrDict):


    f = open(fileLoc, 'rb')
    project = pickle.load(f)
    f.close()

    f = open('%s%s%s%sindexMatrix_99999.pkl'%(project.location, os.path.sep,
					      project.name, os.path.sep), 'rb')

    index_matrix = cPickle.load(f)
    f.close()

    state, county, pumano, tract, bg = geo.state, geo.county, geo.puma5, geo.tract, geo.bg
    print '------------------------------------------------------------------'
    print 'Geography: PUMA ID- %s, Tract ID- %0.2f, BG ID- %s' \
                                                                         %(pumano, float(tract)/100, bg)
    print '------------------------------------------------------------------'

    db = MySQLdb.connect(host = '%s' %project.db.hostname, user = '%s' %project.db.username,
                         passwd = '%s' %project.db.password, db = '%s%s%s' 
                         %(project.name, 'scenario', project.scenario), local_infile=1)

    dbc = db.cursor()

    tii = time.time()
    ti = time.time()

# Identifying the number of housing units in the disaggregate sample
# Make Sure that the file is sorted by hhid
    dbc.execute('select hhid, serialno from hhld_sample order by hhid')
    hhld_sample = numpy.asarray(dbc.fetchall(), numpy.int64)
    hhld_units = dbc.rowcount

    dbc.execute('select hhid, serialno, pnum, personuniqueid from person_sample order by hhid, pnum')
    person_sample = numpy.asarray(dbc.fetchall(), numpy.int64)

    housing_sample = hhld_sample
    housing_units = hhld_units

# Identifying the control variables for the households
    hhld_control_variables = project.hhldVars


# Identifying the number of categories within each control variable for the households
    hhld_dimensions = project.hhldDims

# Checking marginal totals
    hhld_marginals = synthesizer_algorithm.adjusting_sample_joint_distribution.prepare_control_marginals (db, 'hhld', hhld_control_variables,
                                                                                                          varCorrDict,
                                                                                                          project.adjControlsDicts.hhld,
                                                                                    state, county, tract, bg)

    print 'Step 1A: Checking if the marginals totals are non-zero and if they are consistent across variables...'
    print '\tChecking household variables\n'
    synthesizer_algorithm.adjusting_sample_joint_distribution.check_marginals(hhld_marginals, hhld_control_variables)
    
    print 'Step 1B: Checking if the geography has any housing units to synthesize...\n'
    synthesizer_algorithm.adjusting_sample_joint_distribution.check_for_zero_housing_totals(hhld_marginals)

# Reading the parameters
    parameters = project.parameters

#______________________________________________________________________
# Running IPF for Households
    print 'Step 2A: Running IPF procedure for Households... '
    hhld_objective_frequency, hhld_estimated_constraint = synthesizer_algorithm.ipf_nosql.ipf_config_run(db, 'hhld', hhld_control_variables, varCorrDict, 
                                                                             project.adjControlsDicts.hhld,
                                                                             hhld_dimensions, 
                                                                             state, county, pumano, tract, bg, 
                                                                             parameters)
    print 'IPF procedure for Households completed in %.2f sec \n'%(time.time()-ti)
    ti = time.time()

#______________________________________________________________________
# Creating the weights array
    print 'Step 3: Running IPU procedure for obtaining weights that satisfy Household constraints... '
    dbc.execute('select rowno from sparse_matrix1_%s group by rowno'%(99999))
    result = numpy.asarray(dbc.fetchall())[:,0]

    print 'Number of housing units - %s' %housing_units
#______________________________________________________________________
# Creating the control array
    total_constraint = hhld_estimated_constraint[:,0]

#______________________________________________________________________
# Creating the sparse array
    dbc.execute('select * from sparse_matrix1_%s' %(99999))
    sp_matrix = numpy.asarray(dbc.fetchall())


#______________________________________________________________________
# Running the heuristic algorithm for the required geography
    weightsDef = numpy.ones((1,housing_units), dtype = float)[0] * -99
    weightsDef[result]=1
    if project.parameters.ipuProcedure == "ProportionalUpdating":
	print 'Employing the proportional updating procedure for reallocating sample weights', project.parameters.ipuProcedure
    	iteration, weights, conv_crit_array, wts_array = synthesizer_algorithm.heuristic_algorithm_nogqs_noper.heuristic_adjustment(db, 0, index_matrix, weightsDef, total_constraint, sp_matrix, parameters)
    elif project.parameters.ipuProcedure == 'EntropyUpdating':
	print 'Employing the entropy-based updating procedure for reallocating sample weights', project.parameters.ipuProcedure
    	iteration, weights, conv_crit_array, wts_array = synthesizer_algorithm.heuristic_algorithm_nogqs_noper.ipu_entropy(db, 0, index_matrix, weightsDef, total_constraint, sp_matrix, parameters)

    print 'IPU procedure was completed in %.2f sec\n'%(time.time()-ti)
    ti = time.time()
#_________________________________________________________________
    print 'Step 4: Creating the synthetic households and individuals...'
# creating whole marginal values
    hhld_order_dummy = synthesizer_algorithm.adjusting_sample_joint_distribution.create_aggregation_string(hhld_control_variables)
    hhld_frequencies = synthesizer_algorithm.drawing_households.create_whole_frequencies(db, 'hhld', hhld_order_dummy, pumano, tract, bg, parameters)

    frequencies = hhld_frequencies[:,0]
    housing_objective_frequency = hhld_objective_frequency[:,0]

#______________________________________________________________________
# Sampling Households and choosing the draw with the best match with with the objective distribution

    ti = time.time()

    f = open('%s%s%s%spIndexMatrix.pkl'%(project.location, os.path.sep,
					 project.name, os.path.sep), 'rb')

    p_index_matrix = cPickle.load(f)

    f.close()

    print 'pIndexMatrix in - %.4f' %(time.time()-ti)


    hhidRowDict = synthesizer_algorithm.drawing_households.hhid_row_dictionary(housing_sample) # row in the master matrix - hhid
    rowHhidDict = synthesizer_algorithm.drawing_households.row_hhid_dictionary(p_index_matrix) # hhid - row in the person index matrix


    p_value = 0
    max_p = 0
    min_chi = 1e10
    draw_count = 0
    while(p_value < parameters.synPopPTol and draw_count < parameters.synPopDraws):
        draw_count = draw_count + 1
        #synthetic_housing_units = synthesizer_algorithm.drawing_households.drawing_housing_units_nogqs(db, frequencies, weights, index_matrix, sp_matrix, 0, drawingProcedure=project.parameters.drawingProcedure)
        synthetic_housing_units = synthesizer_algorithm.drawing_households.drawing_housing_units_nogqs(db, frequencies, weights, index_matrix, 
									   sp_matrix, 0, 
									   drawingProcedure=project.parameters.drawingProcedure,
									   iteration=draw_count+1)

# Creating synthetic hhld, and person attribute tables

        synthetic_housing_attributes, synthetic_person_attributes = synthesizer_algorithm.drawing_households.synthetic_population_properties(db, geo, synthetic_housing_units, p_index_matrix,
                                                                                                                       housing_sample, person_sample, hhidRowDict,
                                                                                                                       rowHhidDict)



        synth_housing_stat, count_housing, housing_estimated_frequency = synthesizer_algorithm.drawing_households.checking_against_joint_distribution(housing_objective_frequency,
                                                                                                                                synthetic_housing_attributes, hhld_dimensions.prod(),
                                                                                                                                pumano, tract, bg)
        stat = synth_housing_stat
        dof = count_housing - 1

	if dof == 0:
	    p_value = 1
	else:
	    p_value = scipy.stats.chisqprob(stat, dof)

        if p_value > max_p or stat < min_chi:
            max_p = p_value
            max_p_housing_attributes = synthetic_housing_attributes
            max_p_person_attributes = synthetic_person_attributes
            min_chi = stat

    sp_matrix = None

    if draw_count >= parameters.synPopDraws:
        print ('Max Iterations (%d) reached for drawing households with the best draw having a p-value of %.4f'
               %(parameters.synPopDraws, max_p))
        if max_p == 0:
            max_p = p_value
            max_p_housing_attributes = synthetic_housing_attributes
            max_p_person_attributes = synthetic_person_attributes
            min_chi = stat

    else:
        print 'Population with desirable p-value of %.4f was obtained in %d iterations' %(max_p, draw_count)
    print 'draw_count - %s, pvalue - %s, chi value - %s' %(draw_count, max_p, min_chi)
    if max_p_housing_attributes.shape[0] < 2500:
        synthesizer_algorithm.drawing_households.storing_synthetic_attributes1(db, 'housing', max_p_housing_attributes, county, tract, bg)
        synthesizer_algorithm.drawing_households.storing_synthetic_attributes1(db, 'person', max_p_person_attributes, county, tract, bg)
    else:
        synthesizer_algorithm.drawing_households.storing_synthetic_attributes2(db, 'housing', max_p_housing_attributes, county, tract, bg)
        synthesizer_algorithm.drawing_households.storing_synthetic_attributes2(db, 'person', max_p_person_attributes, county, tract, bg)
        

    values = (int(state), int(county), int(tract), int(bg), min_chi, max_p, draw_count, iteration, conv_crit_array[-1])
    synthesizer_algorithm.drawing_households.store_performance_statistics(db, geo, values)

    print 'Number of Synthetic Household/Group quarters - %d' %((max_p_housing_attributes[:,-2]).sum())
    for i in range(len(hhld_control_variables)):
        print '%s variable\'s marginal distribution sum is %d' %(hhld_control_variables[i], round(sum(hhld_marginals[i])))

    db.commit()
    dbc.close()
    db.close()

    print 'Blockgroup synthesized in %.4f s' %(time.time()-tii)

def run_parallel(job_server, project, geoIds, varCorrDict, coreVersion=False):

    fileLoc = "%s/%s/%s.pop" %(project.location, project.name, project.filename)

    start = time.time()
    #print 'Number of geographies is %s'%(len(geoIds))
    modules = ('synthesizer_algorithm.heuristic_algorithm_nogqs_noper',
               'synthesizer_algorithm.drawing_households',
               'synthesizer_algorithm.adjusting_sample_joint_distribution',
               'synthesizer_algorithm.ipf_nosql',
               'synthesizer_algorithm',
               'cPickle',
               'scipy',
               'numpy',
               'pylab',
               'MySQLdb',
               'time',
               'scipy.stats')

    #print 'Using %d cores on the processor' %(job_server.get_ncpus())

    geoIds = [Geography(geo[0], geo[1], geo[3], geo[4], geo[2]) for geo in geoIds]
    
    if coreVersion:
    	project.save()
    
    jobs = [(geo, job_server.submit(configure_and_run, (fileLoc,
                                                        geo,
                                                        varCorrDict), (), modules)) for geo in geoIds]
    for geo, job in jobs:
        job()
    #job_server.print_stats()

    #print ' Total time for %d geographies - %.2f, Timing per geography - %.2f' %(len(geoIds), time.time()-start, (time.time()-start)/len(geoIds))


