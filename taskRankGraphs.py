"""
Creates graphs for task re-ranking metrics from an ECResults checkpoint.
Requires metrics to be available in a recognitionTaskMetrics dict: you can specify this via --storeTaskMetrics.
Or you can attempt to back add them using the --addTaskMetrics function.

Usage: Example script is in taskRankGraphs.

Note: this requires a container with sklearn installed. A sample container is available in /om2/user/zyzzyva/ec/sklearn-container.img
"""

from ec import *
import dill
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plot
from matplotlib.ticker import MaxNLocator
import matplotlib.lines as mlines
from matplotlib.offsetbox import OffsetImage, AnnotationBbox

import matplotlib
plot.style.use('seaborn-whitegrid')
import matplotlib.colors as colors
import matplotlib.cm as cm

import text
from text import LearnedFeatureExtractor
from scipy import stats
from scipy import signal
import itertools

np.set_printoptions(threshold=np.inf) #Print full arrays for debugging

from scipy.stats import entropy
from sklearn import mixture
from sklearn import preprocessing
from sklearn.metrics import log_loss
from sklearn.metrics.cluster import adjusted_rand_score
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.manifold import MDS, TSNE


def loadfun(x):
	with open(x, 'rb') as handle:
		result = dill.load(handle)
	return result

class Bunch(object):
	def __init__(self, d):
		self.__dict__.update(d)

	def __setitem__(self, key, item):
		self.__dict__[key] = item

	def __getitem__(self, key):
		return self.__dict__[key]

relu = 'relu'
tanh = 'tanh'
sigmoid = 'sigmoid'
DeepFeatureExtractor = 'DeepFeatureExtractor'
LearnedFeatureExtractor = 'LearnedFeatureExtractor'
TowerFeatureExtractor = 'TowerFeatureExtractor'

weightMetrics = ['auxiliaryPrimitiveEmbeddings']
metricToHeldout = {
	'startProductions': 'heldoutStartProductions',
	'taskAuxiliaryLossLayer' : 'heldoutAuxiliaryLossLayer',
	'taskLogProductions' : 'heldoutTaskLogProductions',
	'contextualLogProductions' : 'heldoutTaskLogProductions'
}

def parseResultsPath(p):
	def maybe_eval(s):
		try:
			return eval(s)
		except BaseException:
			return s

	p = os.path.basename(p)
	p = p[:p.rfind('.')]
	domain = p[:p.index('_')]
	rest = p.split('_')[1:]
	if rest[-1] == "baselines":
		rest.pop()
	parameters = {ECResult.parameterOfAbbreviation(k): maybe_eval(v)
				  for binding in rest if '=' in binding
				  for [k, v] in [binding.split('=')]}
	parameters['domain'] = domain
	return Bunch(parameters)

def loadResult(path, export=None):
	result = loadfun(path)
	# print("loaded path:", path)
	if not hasattr(result, "recognitionTaskMetrics"):
		print("No recognitionTaskMetrics found, aborting.")
		assert False

	domain = parseResultsPath(path)['domain']
	iterations = parseResultsPath(path)['iterations'] 
	recognitionTaskMetrics = result.recognitionTaskMetrics

	# Create a folder for the domain if it does not exist.
	if export:
		if not os.path.exists(os.path.join(export, domain)):
			os.makedirs(os.path.join(export, domain))
		
	return result, domain, iterations, recognitionTaskMetrics

def softmax(x):
	"""Compute softmax values for each sets of scores in x."""
	return np.exp(x) / np.sum(np.exp(x))

def normalizeAndEntropy(x):
	return entropy(softmax(x))

def exportTaskTimes(
	resultPaths,
	experimentNames,
	timesArg,
	export):
	"""Exports the task time information to the output file"""
	for j, path in enumerate(resultPaths):
		print("Logging result: " + path)
		result, domain, iterations, recognitionTaskMetrics = loadResult(path, export)
		enumerationTimeout = result.parameters['enumerationTimeout'] 

		# Get all the times.
		tasks = [t for t in recognitionTaskMetrics if timesArg in recognitionTaskMetrics[t]]
		taskTimes = [recognitionTaskMetrics[t][timesArg] for t in tasks]

		solvedTaskTimes = [time for time in taskTimes if time is not None ]
		# Replace the Nones with enumeration timeout for the purpose of this.
		taskTimes = [time if time is not None else enumerationTimeout for time in taskTimes]
		taskNames=[t.name for t in tasks]


		# Log Results.
		print("Solved tasks: " + str(len(solvedTaskTimes)))
		print ("Total tasks this round: " + str(len(taskTimes)))
		print("Average solve time (secs): " + str(np.mean(solvedTaskTimes)))
		print("Total time spent solving tasks (secs): " + str(np.sum(taskTimes)))

		for i, name in enumerate(taskNames):
			print("TASK: " + name + " TIME: " + str(taskTimes[i]))


def plotTimeMetrics(
	resultPaths,
	experimentNames,
	outlierThreshold,
	metricsToPlot,
	timesArg,
	export=None):
	"""Plots task times vs. the desired metrics (ie. entropy) for each checkpoint iteration."""


	for j, path in enumerate(resultPaths):
		result, domain, iterations, recognitionTaskMetrics = loadResult(path, export)

		if experimentNames is None:
			experimentName = "none"
		else:
			experimentName = experimentNames[j]

		# Get all the times.
		tasks = [t for t in recognitionTaskMetrics if timesArg in recognitionTaskMetrics[t]]
		taskTimes = [recognitionTaskMetrics[t][timesArg] for t in tasks]
		# Replace the Nones with -1 for the purpose of this.
		taskTimes = [time if time is not None else -1.0 for time in taskTimes]
		taskNames=[t.name for t in tasks]

		for k, metricToPlot in enumerate(metricsToPlot):
			print("Plotting metric: " + metricToPlot)

			taskMetrics = [recognitionTaskMetrics[t][metricToPlot] for t in tasks]

			if outlierThreshold:
				# Threshold to only outlierThreshold stddeviations from the median
				ceiling = outlierThreshold
				noOutliersNames, noOutliersTimes, noOutliersMetrics = [], [], []
				for t in range(len(taskTimes)):
					if taskTimes[t] < ceiling:
						noOutliersTimes.append(taskTimes[t])
						noOutliersMetrics.append(taskMetrics[t])
						noOutliersNames.append(taskNames[t])
				taskNames, taskTimes, taskMetrics = noOutliersNames, noOutliersTimes, noOutliersMetrics

			if outlierThreshold:
				xlabel = ('Recognition Best Times, Outlier Threshold: %d' % (outlierThreshold))
			else:
				xlabel = ('Recognition Best Times')
			title = ("Experiment: %s Domain: %s, Iteration: %d" % (experimentName, domain, iterations))
			ylabel = metricToPlot
			export_name = experimentName + metricToPlot + "_iters_" + str(iterations) + "outlier_threshold_" + str(outlierThreshold) + "_time_plot.png"

			plot.scatter(taskTimes, taskMetrics)
			plot.xlabel(xlabel)
			plot.ylabel(ylabel)
			plot.title(title)
			plot.savefig(os.path.join(export, domain, export_name))

			print("Plotted metric without labels.")

			# Also try plotting with labels.
			times_and_metrics = np.column_stack((taskTimes, taskMetrics))
			plotEmbeddingWithLabels(
				times_and_metrics,
				taskNames,
				title,
				os.path.join(export, domain, "labels_" + export_name),
				xlabel,
				ylabel)

			print("Plotted metric with labels.")
	return


def scatterPlotSimilarities(x, y, exportPath, xlabel=None, ylabel=None):
	plot.figure(figsize=(20,20))
	plot.scatter(x, y)
	if xlabel:
		plot.xlabel(xlabel)
	if ylabel:
		plot.ylabel(ylabel)
	plot.savefig(exportPath)
	return


def plotEmbeddingWithLabels(embeddings, labels, title, exportPath, xlabel=None, ylabel=None):
	plot.figure(figsize=(20,20))
	# Color map based on ordering of the labels.
	cmap = matplotlib.cm.get_cmap('viridis')
	normalize = matplotlib.colors.Normalize(vmin=0, vmax=len(labels))
	colors = [cmap(normalize(value)) for value in range(len(labels))]

	for i, label in enumerate(labels):
		x, y = embeddings[i, 0], embeddings[i, 1]
		plot.scatter(x,y, color=colors[i])
		plot.text(x+0.02, y+0.02, label, fontsize=8)
	plot.title(title)
	if xlabel:
		plot.xlabel(xlabel)
	if ylabel:
		plot.ylabel(ylabel)
	plot.savefig(exportPath)
	return

def plotEmbeddingWithImages(embeddings, images, title, exportPath, xlabel=None, ylabel=None, image_zoom=1):
	"""
	Plots embeddings with thumbnail images.
	Reference: https://www.kaggle.com/gaborvecsei/plants-t-sne
	"""
	fig, ax = plot.subplots(figsize=(45,45))
	artists = []
	for xy, i in zip(embeddings, images):
		x0, y0 = xy
		img = OffsetImage(i, zoom=1)
		ab = AnnotationBbox(img, (x0, y0), xycoords='data', frameon=False)
		artists.append(ax.add_artist(ab))

	ax.update_datalim(embeddings)
	ax.autoscale()

	plot.title(title)
	if xlabel:
		plot.xlabel(xlabel)
	if ylabel:
		plot.ylabel(ylabel)
	print("Saving to: " + exportPath)
	plot.savefig(exportPath)
	return

def makeLogoImage(im):
	im = np.reshape(np.array(im),(128, 128))
	# Make black and white.
	black_mask = im != 0
	white_mask = im == 0
	im[black_mask] = 0
	im[white_mask] = 255

	alpha = np.zeros(im.shape)
	alpha[black_mask] = 255
	# Need to make it the opposite for alpha.
	im = np.dstack([im, im, im, alpha])
	return im

def makeTowerImage(im):
	# Set the black pixels to transparent.
	black_mask = im[:, :, 0] == 0
	alpha = np.ones((256,256)) * 255
	alpha[black_mask] = 0
	im = np.dstack([im, alpha])
	return im

def makeRationalImage(im):
	im = np.reshape(np.array(im),(64, 64))
	# Make black and white.
	black_mask = im != 0
	white_mask = im == 0
	im[black_mask] = 0
	im[white_mask] = 255

	alpha = np.zeros(im.shape)
	alpha[black_mask] = 255
	# Need to make it the opposite for alpha.
	im = np.dstack([im, im, im, alpha])
	return im

def frontierMetric(frontiers):
	primitives = {p
			  for f in frontiers
			  for e in f.entries
			  for p in [e.program]
			  if p.isInvented}
	g = Grammar.uniform(primitives)
	return [f.expectedProductionUses(g) for f in frontiers]

def printTaskExamples(taskType, task):
	print(task.name)
	for example in task.examples:
		if taskType == 'text':
			print("%s -> %s" % ("".join(example[0][0]), "".join(example[1])))
		if taskType == 'list':
			print("%s -> %s" % (str(example[0][0]), str(example[1])))
		else:
			print(example)
	print('\n')

def formattedName(metricToCluster, item):
	if metricToCluster in weightMetrics or isinstance(item, Program):
		raw_name = str(item)
	else:
		raw_name = item.name

	# Replace lambda instances.
	raw_name = raw_name.replace(u'lambda', u'λ')
	if(len(raw_name)) > 100:
		return raw_name[:50] + "\n" + raw_name[50:]
	else:
		return raw_name

def plotTSNE(
	resultPaths,
	experimentNames,
	metricsToCluster,
	applySoftmax,
	tsneLearningRate,
	tsnePerplexity,
	labelWithImages,
	export=None,
	printExamples=None):
	"""Plots TSNE clusters of the given metrics. Requires Sklearn."""

	from sklearn.manifold import TSNE

	if metricsToCluster is None:
		return

	for j, path in enumerate(resultPaths):
		result, domain, iterations, recognitionTaskMetrics = loadResult(path, export)
		if experimentNames is None:
			experimentName = "none"
		else:
			experimentName = experimentNames[j]

		for k, metricToCluster in enumerate(metricsToCluster):
			print("Clustering metric: " + metricToCluster )
			tsne = TSNE(random_state=0, perplexity=tsnePerplexity, learning_rate=tsneLearningRate, n_iter=10000)
			taskNames, taskMetrics = [], []

			for task in sorted(recognitionTaskMetrics.keys(), key=lambda task : formattedName(metricToCluster, task)):
				if metricToCluster in recognitionTaskMetrics[task]:
					if printExamples:
						printTaskExamples(printExamples, task)

					if recognitionTaskMetrics[task][metricToCluster] is not None:
						taskNames.append(formattedName(metricToCluster, task))  
						taskMetrics.append(recognitionTaskMetrics[task][metricToCluster])
			if metricToCluster == 'frontier':
				taskMetrics = [f.expectedProductionUses(result.grammars[-1])
						   for f in taskMetrics] 

			print("Clustering %d tasks with embeddings of shape: %s" % (len(taskMetrics), str(taskMetrics[0].shape)) )
			if applySoftmax:
				taskMetrics = [softmax(metric) for metric in taskMetrics]
			taskNames = np.array(taskNames)
			taskMetrics = np.array(taskMetrics)
			metricNorms = (taskMetrics*taskMetrics).sum(1)**0.5
			taskMetrics = taskMetrics/np.reshape(metricNorms, (metricNorms.shape[0], 1))
			print(taskNames.shape, taskMetrics.shape)
			
			clusteredTaskMetrics = tsne.fit_transform(taskMetrics)
			title = ("Metric: %s, Domain: %s, Experiment: %s, Iteration: %d" % (metricToCluster, domain, experimentName, iterations))

			if labelWithImages:
				images = []
				for i, task in enumerate(sorted(filter(lambda mt: isinstance(mt, Task), recognitionTaskMetrics.keys()), key=lambda task : task.name)): # Enumerate in same order as sorted tasks.
					if 'taskImages' not in recognitionTaskMetrics[task] and domain == 'tower': recognitionTaskMetrics[task]['taskImages'] = task.getImage(pretty=True) # BUG: this shouldn't be necessaryd
					if 'taskImages' not in recognitionTaskMetrics[task] and domain == 'rational': recognitionTaskMetrics[task]['taskImages'] = task.features
					if 'taskImages' not in recognitionTaskMetrics[task] and domain == 'logo': recognitionTaskMetrics[task]['taskImages'] = task.highresolution
					im = np.array(recognitionTaskMetrics[task]['taskImages'])
					if domain == 'logo':
						im = makeLogoImage(im)
					elif domain == 'tower':
						im = makeTowerImage(im)
					elif domain == 'rational':
						im = makeRationalImage(im)
					images.append(im)

				plotEmbeddingWithImages(clusteredTaskMetrics, 
					images, 
					title, 
					os.path.join(export, domain, experimentName + metricToCluster + "_iters_" + str(iterations) + "_tsne_images.png"))
			else:
				plotEmbeddingWithLabels(clusteredTaskMetrics, 
					taskNames, 
					title, 
					os.path.join(export, domain, experimentName + metricToCluster + "_iters_" + str(iterations) + "_tsne_labels.png"))

def invMap(curr_map):
		inv_map = {}
		for k, v in curr_map.items():
			inv_map[v] = inv_map.get(v, [])
			inv_map[v].append(k)
		return inv_map

def getGroundTruthStarts(groundTruthCheckpoints):
	"""Ground truth starts: the start production for the top-ranked frontier in the test and train task solutions."""
	def getFrontierStart(frontiers):
		# Get the top programs
		topEntry = sorted(frontiers.entries, key=lambda e:e.logLikelihood, reverse=True)[0]
		p = topEntry.program
		while p.isAbstraction: p = p.body
		while p.isApplication: p = p.f
		return p

	frontierStarts = []
	for j, path in enumerate(groundTruthCheckpoints):
			result, domain, iterations, recognitionTaskMetrics = loadResult(path)
			# Solved training tasks.
			taskSolutions = result.taskSolutions
			trainToStarts= {task: getFrontierStart(frontiers) for task, frontiers in taskSolutions.items() if len(frontiers) > 0}
			startToTrains = invMap(trainToStarts)

			# Solved testing tasks.
			testToStarts={}
			for task in sorted(recognitionTaskMetrics.keys(), key=lambda task : formattedName('frontier', task)):
				if 'frontier'in recognitionTaskMetrics[task] and task not in trainToStarts:
					if len(recognitionTaskMetrics[task]['frontier']) > 0:
						testToStarts[task] = getFrontierStart(recognitionTaskMetrics[task]['frontier'])
			startToTests = invMap(testToStarts)
			frontierStarts.append([trainToStarts, startToTrains, testToStarts, startToTests])
	return frontierStarts

def DPGMM(metricsDict, groundTruths):
	if len(metricsDict) < 1:
		return (None, None, None)
	taskMetrics = np.array([metricsDict[task] for task in metricsDict.keys()])
	metricNorms = (taskMetrics*taskMetrics).sum(1)**0.5
	taskMetrics = taskMetrics/np.reshape(metricNorms, (metricNorms.shape[0], 1))
	dpgmm = mixture.BayesianGaussianMixture(n_components=len(groundTruths),
								   covariance_type='full').fit(taskMetrics)
	clusters = dpgmm.predict(taskMetrics)
	taskToCluster = {}
	for j, task in enumerate(metricsDict.keys()):
		taskToCluster[task] = clusters[j]
	clusterToTasks = invMap(taskToCluster)
	return (metricsDict.keys(), clusters, taskToCluster)

def getExpectedProductionUses(checkpoints, groundTruthStarts):
	"""Extract out the predicted productions from the recognition model for the ground truth start tasks."""
	allEPs = []
	for j, path in enumerate(checkpoints):
		result, domain, iterations, recognitionTaskMetrics = loadResult(path)
		trainToStarts, startToTrains, testToStarts, startToTests = groundTruthStarts[j]

		trainExpectedProductions = {}
		testExpectedProductions = {}
		for task in sorted(recognitionTaskMetrics.keys(), key=lambda task : formattedName('frontier', task)):

			if 'expectedProductionUses'in recognitionTaskMetrics[task]:
				trainExpectedProductions[task] = recognitionTaskMetrics[task]['expectedProductionUses']
			elif 'frontier'in recognitionTaskMetrics[task] and task in testToStarts:
				testExpectedProductions[task] = recognitionTaskMetrics[task]['frontier'].expectedProductionUses(result.grammars[-1])

		allEPs.append([DPGMM(trainExpectedProductions, startToTrains), DPGMM(testExpectedProductions, startToTests)])
	return allEPs


def getSimilarities(rawMetrics, applySoftmax):
	"""Assumes a dict from task: metric vector."""
	if len(rawMetrics) < 1:
		return None
	taskMetrics = np.array(rawMetrics)
	# metricNorms = (taskMetrics*taskMetrics).sum(1)**0.5
	# taskMetrics = taskMetrics/np.reshape(metricNorms, (metricNorms.shape[0], 1))

	sim = cosine_similarity(taskMetrics, taskMetrics)
	np.fill_diagonal(sim, 0)

	# if applySoftmax:
	# 	# Normalize the rows of the matrix.
	# 	sim = np.apply_along_axis(softmax, 1, sim)

	# Normalize the matrix rows.

	return sim
	
def plotHeatMap(cm, classes,
						  title='Confusion matrix',
						  cmap=plot.cm.Blues,
						  exportPath=None):
	"""
	This function prints and plots the confusion matrix.
	Normalization can be applied by setting `normalize=True`.
	"""
	plot.figure(figsize=(20,20))

	plot.imshow(cm, interpolation='nearest', cmap=cmap)
	plot.title(title)
	tick_marks = np.arange(len(classes))
	plot.xticks(tick_marks, classes, rotation=90, fontsize=8)
	plot.yticks(tick_marks, classes, fontsize=8)

	print("Saving to: " + exportPath)
	plot.savefig(exportPath)
	return


def getClusterIntersections(allMetricClusters):
	def getIntersections(keys, taskToClusters):
		intersections = []
		for (task1, task2) in itertools.combinations(keys, 2):
			isSame = True
			for clusterDict in taskToClusters:
				if task1 in clusterDict and task2 in clusterDict:
					if clusterDict[task1] != clusterDict[task2]:
						isSame = False
			if isSame:
				shouldAppend=True
				for j, intersection in enumerate(intersections):
					if task1.name in intersection or task2.name in intersection:
						shouldAppend=False
						intersections[j].union((task1.name, task2.name))
						break
				if shouldAppend:
					intersections.append(set((task1.name, task2.name)))
		print(intersections)
		assert False

	(trainKeys, _, _), (testKeys, _, _) = allMetricClusters[0]
	trainTaskToClusters = [trainDict for (trainKeys, _, trainDict), (testKeys, _, testDict) in allMetricClusters]
	testTaskToClusters = [testDict for (trainKeys, _, trainDict), (testKeys, _, testDict) in allMetricClusters]
	print("Train intersections:")
	getIntersections(trainKeys, trainTaskToClusters)
	if len(testKeys) > 0:
		getIntersections(testKeys, testTaskToClusters)



def clusteringAnalysis(
	checkpoints,
	groundTruthCheckpoints,
	clusteringMetrics,
	compareToGroundTruthStarts,
	compareToExpectedProductionUses,
	clusteringMethod='dpgmm',
	min_k=1,
	max_k=None,
	export=None):
	"""Clustering analysis on the results of a given metric. 

	If more than one checkpoint is provided, also calculates sets of tasks that appeared in the same cluster amongst the checkpoints 
	by the size of the set and the number of checkpoints that grouped the same set into the same cluster.
	Exports a pickle file with the results.
	"""
	print("Clustering on: %d checkpoints" % len(checkpoints))
	# Extract out the ground truth starts for the frontiers.
	groundTruthStarts = getGroundTruthStarts(groundTruthCheckpoints)

	if compareToExpectedProductionUses:
		groundTruthEPs = getExpectedProductionUses(groundTruthCheckpoints, groundTruthStarts)

	for metric in clusteringMetrics:
		if metric in metricToHeldout:
			heldoutMetric = metricToHeldout[metric]
		else:
			heldoutMetric = "None"
		print("Clustering on metric: " + metric + " heldoutMetric: " + metricToHeldout[metric])	
		allMetricClusters = []
		for j, path in enumerate(checkpoints):
			result, domain, iterations, recognitionTaskMetrics = loadResult(path)
			trainToStarts, startToTrains, testToStarts, startToTests = groundTruthStarts[j]
			
			trainMetrics, testMetrics = {}, {}
			for task in sorted(recognitionTaskMetrics.keys(), key=lambda task : formattedName('frontier', task)):
				if metric in recognitionTaskMetrics[task] and task in trainToStarts:
					trainMetrics[task] = recognitionTaskMetrics[task][metric]
				elif heldoutMetric in recognitionTaskMetrics[task] and task in testToStarts:
					testMetrics[task] = recognitionTaskMetrics[task][heldoutMetric]

			if trainMetrics.keys() != trainToStarts.keys():
				print("WARNING: TRAIN KEYS DO NOT MATCH GROUND TRUTH.")
				print(path)
			if testMetrics.keys() != testToStarts.keys():	
				print("WARNING: TEST KEYS DO NOT MATCH GROUND TRUTH.")

			allMetricClusters.append([DPGMM(trainMetrics, startToTrains), DPGMM(testMetrics, startToTests)])

		# Compare to ground truth
		if compareToGroundTruthStarts:
			groundTruthStartsRITrain, groundTruthStartsRITest = [], []
			for j, path in enumerate(checkpoints):
				trainToStarts, startToTrains, testToStarts, startToTests = groundTruthStarts[j]
				(_, trainLabels, _), (_, testLabels, _) = allMetricClusters[j]
				# Convert labels to numerical labels
				trainGroundTruthLabels = preprocessing.LabelEncoder().fit_transform([str(val) for val in trainToStarts.values()])
				groundTruthStartsRITrain.append(adjusted_rand_score(trainGroundTruthLabels, trainLabels))

				if testLabels:
					testGroundTruthLabels = preprocessing.LabelEncoder().fit_transform([str(val) for val in testToStarts.values()])
					groundTruthStartsRITest.append(adjusted_rand_score(testGroundTruthLabels, testLabels))

			print("Comparison to ground truth starts RI train: %s" % str(groundTruthStartsRITrain))
			print("Comparison to ground truth starts RI test: %s" % str(groundTruthStartsRITest))

		# Compare to expected production
		if compareToExpectedProductionUses:
			groundTruthEPTrain, groundTruthEPTest = [], []
			for j, path in enumerate(checkpoints):
				(_, trainTrueLabels, _), (_, testTrueLabels, _) = groundTruthEPs[j]
				(_, trainLabels, _), (_, testLabels, _) = allMetricClusters[j]
				groundTruthEPTrain.append(adjusted_rand_score(trainTrueLabels, trainLabels))
				if testLabels:
					groundTruthEPTest.append(adjusted_rand_score(testTrueLabels, testLabels))
			print("Comparison to ground truth EP RI train: %s" % str(groundTruthEPTrain))
			print("Comparison to ground truth EP RI test: %s" % str(groundTruthEPTest))

		# Compare to each other to find agreed upon sets
		getClusterIntersections(allMetricClusters)

def getMDSOrdering(expectedProductionUses):
	embedding = MDS(random_state=0, n_components=1)
	X_transformed = embedding.fit_transform(expectedProductionUses)
	ordering = np.argsort(np.squeeze(X_transformed))
	return ordering

def getExpectedProductionSimilarities(checkpoints, ordering, applySoftmax):
	allEPs = []
	for j, path in enumerate(checkpoints):
		result, domain, iterations, recognitionTaskMetrics = loadResult(path)
		# Solved training tasks.
		trainTasks = [task for task, frontiers in result.taskSolutions.items() if len(frontiers) > 0]
		trainNames, trainExpected = [], []
		testNames, testExpected = [], []
		for task in sorted(recognitionTaskMetrics.keys(), key=lambda task : formattedName('frontier', task)):
			if 'expectedProductionUses'in recognitionTaskMetrics[task]:
				trainNames.append(formattedName('frontier', task)) 
				trainExpected.append(recognitionTaskMetrics[task]['expectedProductionUses'])
			elif 'frontier'in recognitionTaskMetrics[task] and task not in trainTasks:
				testNames.append(formattedName('frontier', task)) 
				testExpected.append(recognitionTaskMetrics[task]['frontier'].expectedProductionUses(result.grammars[-1]))

		trainNames, trainExpected, testNames, testExpected = np.array(trainNames), np.array(trainExpected), np.array(testNames), np.array(testExpected)
		if ordering == 'MDS':
			print("Fitting an MDS ordering.")
			# Fit an MDS to one component and use to sort.
			trainOrdering, testOrdering = getMDSOrdering(trainExpected), getMDSOrdering(testExpected)
			trainNames, trainExpected, testNames, testExpected = trainNames[trainOrdering], trainExpected[trainOrdering], testNames[testOrdering], testExpected[testOrdering]


		allEPs.append([(trainNames, trainExpected, getSimilarities(trainExpected, applySoftmax)), (testNames, testExpected, getSimilarities(testExpected, applySoftmax))])

		print("Found %d ground truth train and %d test." %(len(trainExpected), len(testExpected)))
	return allEPs

def getSimilarityMetrics(similarityMetric, recognitionTaskMetrics, trainNames, testNames, applySoftmax):
	newRecognitionMetrics = {formattedName('frontier', task) : value for task, value in recognitionTaskMetrics.items()}
	trainMetrics = [newRecognitionMetrics[taskName][similarityMetric] for taskName in trainNames if similarityMetric in newRecognitionMetrics[taskName] ] 
	if similarityMetric in metricToHeldout:
		heldoutMetric = metricToHeldout[similarityMetric]
		testMetrics = [newRecognitionMetrics[taskName][heldoutMetric] for taskName in testNames if heldoutMetric in newRecognitionMetrics[taskName] ]
	if applySoftmax:
		trainMetrics = [softmax(trainMetric) for trainMetric in trainMetrics]
		testMetrics = [softmax(testMetric) for testMetric in testMetrics]
	return (trainMetrics, getSimilarities(trainMetrics, applySoftmax)), (testMetrics, getSimilarities(testMetrics, applySoftmax))

def meanCorrelation(pk,qk):
	correlations = []
	for i in range(pk.shape[0]):
		correlations.append(np.correlate(pk[i,], qk[i,]))

	return np.mean(correlations)




def similarityAnalysis(
	checkpoints,
	groundTruthCheckpoints,
	experimentNames,
	similarityMetrics,
	applySoftmax,
	similarityWithTSNE,
	ordering=None,
	exportPath=None):
	"""Create similarity matrices for the given metric and compare similarities of pairs with the ground truth."""
	groundTruthSimilarities = getExpectedProductionSimilarities(groundTruthCheckpoints, ordering, applySoftmax)

	# Create similarity matrices for each of the metrics.
	for j, path in enumerate(checkpoints):
		result, domain, iterations, recognitionTaskMetrics = loadResult(path)
		((trainNames, trainExpected, trainTruthSims), (testNames, testExpected, testTruthSims)) = groundTruthSimilarities[j]

		for similarityMetric in similarityMetrics:
			(trainMetrics, trainMetricSims), (testMetrics, testMetricSims) = getSimilarityMetrics(similarityMetric, recognitionTaskMetrics, trainNames, testNames, applySoftmax) 

			# Save the metric similarity matrices.
			plotHeatMap(trainMetricSims, trainNames, exportPath=os.path.join(exportPath, experimentNames[j] +"_it_%d_%s_train_similarities.png" % (iterations, similarityMetric)))
			scatterPlotSimilarities(trainTruthSims.flatten(), trainMetricSims.flatten(), exportPath=os.path.join(exportPath, experimentNames[j] +"_it_%d_%s_train_scatter.png" % (iterations, similarityMetric)), xlabel="Expected Production Uses", ylabel=similarityMetric)
			
			if testMetrics:
				plotHeatMap(testMetricSims, testNames, exportPath=os.path.join(exportPath, experimentNames[j] +"_it_%d_%s_test_similarities.png" % (iterations, similarityMetric)))
				scatterPlotSimilarities(testTruthSims.flatten(), testMetricSims.flatten(), exportPath=os.path.join(exportPath, experimentNames[j] +"_it_%d_%s_test_scatter.png" % (iterations, similarityMetric)), xlabel="Expected Production Uses", ylabel=similarityMetric)

			if similarityWithTSNE:
				# Also do TSNE with the given ordering.
				tsne = TSNE(random_state=0, perplexity=30, learning_rate=350, n_iter=10000)
				clusteredTrainMetrics = tsne.fit_transform(trainMetrics)
				plotEmbeddingWithLabels(clusteredTrainMetrics, 
					trainNames, 
					similarityMetric, 
					os.path.join(exportPath, experimentNames[j] +"_it_%d_%s_train_tsne.png" % (iterations, similarityMetric)))
				if testMetrics:
					clusteredTestMetrics = tsne.fit_transform(testMetrics)
					plotEmbeddingWithLabels(clusteredTestMetrics, 
						testNames, 
						similarityMetric, 
						os.path.join(exportPath, experimentNames[j] +"_it_%d_%s_test_tsne.png" % (iterations, similarityMetric)))


			from sklearn.metrics import mean_squared_error
			print("Experiment train: %s, it=%s, metric %s, mse %f" % (experimentNames[j], iterations, similarityMetric, mean_squared_error(trainTruthSims, trainMetricSims)))
			if testMetrics:
				print("Experiment test: %s, it=%s, metric %s, mse %f" % (experimentNames[j], iterations, similarityMetric, mean_squared_error(testTruthSims, testMetricSims)))

		# Sanity check clustering
		if similarityWithTSNE:
			tsne = TSNE(random_state=0, perplexity=30, learning_rate=350, n_iter=10000)
			clusteredGTMetrics = tsne.fit_transform(trainExpected)
			plotEmbeddingWithLabels(clusteredTrainMetrics, 
					trainNames, 
					"Expected Productions", 
					os.path.join(exportPath, experimentNames[j] + "_gt_train_tsne.png"))
			if testMetrics:
				clusteredGTMetrics = tsne.fit_transform(testExpected)
				plotEmbeddingWithLabels(clusteredTestMetrics, 
						testNames, 
						"Expected Productions", 
						os.path.join(exportPath, experimentNames[j] + "_gt_test_tsne.png"))


			# TODO: how to compare the two metrics.



if __name__ == "__main__":
	import sys

	import argparse

	parser = argparse.ArgumentParser(description = "")
	parser.add_argument("--checkpoints",nargs='+')
	parser.add_argument ("--experimentNames", nargs='+', type=str, default=None)
	parser.add_argument("--metricsToPlot", nargs='+',type=str)
	parser.add_argument("--times", type=str, default='recognitionBestTimes')
	parser.add_argument("--exportTaskTimes", type=bool)
	parser.add_argument("--outlierThreshold", type=float, default=None)

	#TSNE 
	parser.add_argument("--metricsToCluster", nargs='+', type=str, default=None)
	parser.add_argument("--tsneLearningRate", type=float, default=250.0)
	parser.add_argument("--tsnePerplexity", type=float, default=30.0)
	parser.add_argument("--labelWithImages", type=bool, default=None)
	parser.add_argument('--printExamples', type=str, default=None)
	parser.add_argument('--applySoftmax',  default=False, action="store_true")

	# Clustering analysis
	parser.add_argument("--clusteringAnalysisMetrics", nargs='+', type=str, default=None)
	parser.add_argument("--groundTruthCheckpoints", nargs='+', default=None)
	parser.add_argument("--clusteringMethod", type=str, default='dpgmm')
	parser.add_argument("--compareToGroundTruthStarts", default=False, action='store_true')
	parser.add_argument("--compareToExpectedProductionUses", default=False, action='store_true')

	# Similarity matrix analysis
	parser.add_argument("--similarityAnalysisMetrics", nargs='+', type=str, default=None)
	parser.add_argument("--similarityOrdering", type=str, default=None)
	parser.add_argument("--similarityWithTSNE", default=False, action="store_true")



	parser.add_argument("--export","-e",
						type=str, default='data')

	arguments = parser.parse_args()

	if arguments.similarityAnalysisMetrics:
		similarityAnalysis(arguments.checkpoints,
							arguments.groundTruthCheckpoints,
							arguments.experimentNames,
							arguments.similarityAnalysisMetrics,
							arguments.applySoftmax,
							arguments.similarityWithTSNE,
							ordering=arguments.similarityOrdering,
							exportPath=arguments.export)


	if arguments.clusteringAnalysisMetrics:
		clusteringAnalysis(arguments.checkpoints,
							arguments.groundTruthCheckpoints,
							arguments.clusteringAnalysisMetrics,
							arguments.compareToGroundTruthStarts,
							arguments.compareToExpectedProductionUses)

	if arguments.exportTaskTimes:
		exportTaskTimes(arguments.checkpoints,
						arguments.experimentNames,
						arguments.times,
						arguments.export)

	if arguments.metricsToPlot:
		plotTimeMetrics(arguments.checkpoints,
						arguments.experimentNames,
						arguments.outlierThreshold,
						arguments.metricsToPlot,
						arguments.times,
						arguments.export)

	if arguments.metricsToCluster:
		plotTSNE(arguments.checkpoints,
				 arguments.experimentNames,
				 arguments.metricsToCluster,
				 arguments.applySoftmax,
				 arguments.tsneLearningRate,
				 arguments.tsnePerplexity,
				 arguments.labelWithImages,
				 arguments.export,
				 arguments.printExamples)
