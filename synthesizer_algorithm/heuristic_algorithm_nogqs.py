# PopGen 1.1 is A Synthetic Population Generator for Advanced
# Microsimulation Models of Travel Demand
# Copyright (C) 2009, Arizona State University
# See PopGen/License

# Running IPF on Person and Household data

from psuedo_sparse_matrix import generate_index_matrix
import time
import MySQLdb
from math import exp, log
from numpy import asarray as arr
from numpy import ones, zeros, power
from scipy.optimize import fsolve

def ipu(db, pumano, index_matrix, weights, control, sp_matrix, parameters):
    pass

def optimizing_function(root, weights, xC, const): 
    scal = (xC*weights*power(root, xC)).sum() - const
    #print 'Scalar - ', scal
    return scal

def find_root(xC, const, weights):
    root = 1
    optRoot = fsolve(optimizing_function, root, args=(weights, xC, const))
    #print 'Root = ', optRoot
    return optRoot



def ipu_entropy(db, pumano, index_matrix, weights, control, sp_matrix, parameters):
    print 'Entropy Procedure'
    dbc = db.cursor()
    ti =time.time()

# Adjusting for household types
    dbc.execute('select hhlduniqueid from hhld_sample group by hhlduniqueid')
    hhld_colno = dbc.rowcount

    hh_colno = hhld_colno

    tot_colno = index_matrix.shape[0]

    iteration = 0
    conv_criterion_array = []
    wts_personadj = []
    conv_criterion = 0
    convergence = 0
    #    print 'Starting the Heuristic Procedure'
    print 'iteration, Sum_Wts_Hhld_Adj, Sum_Wts_Person_Adj, Constraints, e-statistic, convergence (0/1)'
    
    while (iteration < parameters.ipuIter and convergence == 0):
        ti = time.time()
        iteration = iteration + 1
	
    # Adjusting for person types
	for i in index_matrix[hh_colno:,:]:
	    xC = sp_matrix[i[1]-1:i[2], 4]
	    const = control[i[0]-4]
	    weightsC = weights[sp_matrix[i[1]-1:i[2], 2]]	    	    
	
	    optRoot = find_root(xC, const, weightsC)
	    weights[sp_matrix[i[1]-1:i[2], 2]] = weights[sp_matrix[i[1]-1:i[2], 2]] * power(optRoot, sp_matrix[i[1]-1:i[2], 4])
	
        wts_personadj.append(weights.sum())

    # Adjusting for housing types including both household and group quarters
        for i in index_matrix[:hh_colno,:]:
	    xC = sp_matrix[i[1]-1:i[2], 4]
	    const = control[i[0]-4]
	    weightsC = weights[sp_matrix[i[1]-1:i[2], 2]]	    	    
	
	    optRoot = find_root(xC, const, weightsC)
	    weights[sp_matrix[i[1]-1:i[2], 2]] = weights[sp_matrix[i[1]-1:i[2], 2]] * power(optRoot, sp_matrix[i[1]-1:i[2], 4])


    # Creating the evaluation statistic
        for i in index_matrix[hh_colno:,:]:
            dummy = ((weights[sp_matrix[i[1]-1:i[2], 2]] * sp_matrix[i[1]-1:i[2], 4]).sum() - control[i[0]-4]) / control[i[0]-4]
            conv_criterion = conv_criterion + abs(dummy)


    # CHECK FOR THE STATIONARY VALUES FOR THE INDEX ERROR THAT IS BEING PROMPTED

        conv_criterion = conv_criterion / ( tot_colno - hh_colno)
        conv_criterion_array.append(conv_criterion)
        if iteration >=2:
            convergence = abs(conv_criterion_array[-1] - conv_criterion_array[-2])
            if convergence < parameters.ipuTol:
                convergence = 1
            else:
                convergence = 0
        conv_criterion = 0
	print '%d, %.4f, %.4f, %d, %.4f'%(iteration, (weights).sum(), wts_personadj[-1], tot_colno, conv_criterion_array[-1])
    conv_criterion = conv_criterion / ( tot_colno - hh_colno)
    print '%d, %.4f, %.4f, %d, %.4f, %d'%(iteration, (weights).sum(), wts_personadj[-1], tot_colno, conv_criterion_array[-1], convergence)
    return iteration, weights, conv_criterion_array, wts_personadj


def heuristic_adjustment(db, pumano, index_matrix, weights, control, sp_matrix, parameters):
    dbc = db.cursor()
    ti =time.clock()


# Adjusting for household types
    dbc.execute('select hhlduniqueid from hhld_sample group by hhlduniqueid')
    hhld_colno = dbc.rowcount

    hh_colno = hhld_colno
    tot_colno = index_matrix.shape[0]

    iteration = 0
    conv_criterion_array = []
    wts_personadj = []
    conv_criterion = 0
    convergence = 0
#    print 'Starting the Heuristic Procedure'
    print 'iteration, Sum_Wts_Hhld_Adj, Sum_Wts_Person_Adj, Constraints, e-statistic, convergence (0/1)'
    while (iteration < parameters.ipuIter and convergence == 0):
        ti = time.clock()
        iteration = iteration + 1

# Adjusting for person types
        for i in index_matrix[hh_colno:,:]:

            adjustment = control[i[0]-4] / (weights[sp_matrix[i[1]-1:i[2], 2]] * sp_matrix[i[1]-1:i[2], 4]).sum()
            weights[sp_matrix[i[1]-1:i[2], 2]] = weights[sp_matrix[i[1]-1:i[2], 2]] * adjustment
        wts_personadj.append((weights).sum())

# Adjusting for housing types including both household and group quarters
        for i in index_matrix[:hh_colno,:]:
            if control[i[0]-4] == 0:
                print 'Zero Control'
            adjustment = control[i[0]-4] / (weights[sp_matrix[i[1]-1:i[2], 2]]).sum()
            weights[sp_matrix[i[1]-1:i[2], 2]] = weights[sp_matrix[i[1]-1:i[2], 2]] * adjustment


# Creating the evaluation statistic
        for i in index_matrix[hh_colno:,:]:
            dummy = ((weights[sp_matrix[i[1]-1:i[2], 2]] * sp_matrix[i[1]-1:i[2], 4]).sum() - control[i[0]-4]) / control[i[0]-4]
            conv_criterion = conv_criterion + abs(dummy)


# CHECK FOR THE STATIONARY VALUES FOR THE INDEX ERROR THAT IS BEING PROMPTED


        """ Use the following lines if you are not going to use the whole PUMS sample for estimating weights for a small geography say you
        will just use the PUMS corresponding to the PUMA to which the small geography belongs
        sum_heuristic =0
        for i in weights:
            if i <0 and i <>-99:
                print 'wrong weight modified'
            if i>=0:
                sum_heuristic = sum_heuristic +i
        """
        conv_criterion = conv_criterion / ( tot_colno - hh_colno)
        conv_criterion_array.append(conv_criterion)
        if iteration >=2:
            convergence = abs(conv_criterion_array[-1] - conv_criterion_array[-2])
            if convergence < parameters.ipuTol:
                convergence = 1
            else:
                convergence = 0
        conv_criterion = 0
    conv_criterion = conv_criterion / ( tot_colno - hh_colno)
    print '%d, %.4f, %.4f, %d, %.4f, %d'%(iteration, (weights).sum(), wts_personadj[-1], tot_colno, conv_criterion_array[-1], convergence)
    return iteration, weights, conv_criterion_array, wts_personadj

# How to deal with the fact that zero marginals will multiply the weights out to zeros

if __name__ == '__main__':
    pass
