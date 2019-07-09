'''
    Implementation of the Breaking Ties heuristic
    (Luo et al. 2005: "Active Learning to Recognize Multiple Types of Plankton." JMLR 6, 589-613.)

    2019 Benjamin Kellenberger
'''

from ai.al.functional.noarch.functional import _breaking_ties

class BreakingTies:
    
    def __init__(self, config, dbConnector, fileServer, options):
        pass

    
    def rank(self, data, **kwargs):
        
        # iterate through the images and predictions
        for imgID in data.keys():
            if 'predictions' in data[imgID]:
                for predID in data[imgID]['predictions'].keys():
                    pred = data[imgID]['predictions'][predID]
                    btVal = _breaking_ties(pred)
                    data[imgID]['predictions'][predID]['priority'] = btVal
        return data