#!/usr/bin/python3
# -*- coding: utf-8 -*-

import importlib
import sys
import os
import filter_blacklist

#
# Extract Transform Load (ETL):
#

# Runs the configured plugins with parameters from configs it reads
#
# Then exports data like content, data enrichment or analytics results generated by the plugins
# to index or database

class ETL(object):
	
	def __init__(self, plugins=[], verbose=False ):

		self.verbose = verbose
		
		self.config = {}

		self.config['plugins'] = plugins

		self.set_configdefaults()


	def set_configdefaults(self):
	
		#
		# Standard config
		#
		# Do not edit config here! Overwrite options in /etc/opensemanticsearch/etl or connector configs
		#

		self.config['plugins'] = [ 'enhance_extract_text_tika_server' ]
		self.config['export'] = 'export_solr'
		self.config['regex_lists'] = []
		
		self.config['raise_pluginexception'] = False
		
		
	def init_exporter(self):

		exporter = self.config['export']

		module = importlib.import_module(exporter)
		objectreference = getattr(module, exporter)
		self.exporter = objectreference(self.config)
	

	def read_configfile(self, configfile):
		result = False
		
		if os.path.isfile(configfile):
			config = self.config
			exec(open(configfile).read(), locals())
			self.config = config
	
			result = True

		#
		# sort added plugins because of dependencies
		#
		
		# OCR has to be done before language detection, since content maybe only scanned text within images
		if "enhance_detect_language_tika_server" in self.config['plugins'] and "enhance_pdf_ocr" in self.config['plugins']:
			if self.config['plugins'].index("enhance_pdf_ocr") > self.config['plugins'].index("enhance_detect_language_tika_server"):
				# remove after
				self.config['plugins'].remove("enhance_pdf_ocr")
				# add before
				self.config['plugins'].insert(self.config['plugins'].index("enhance_detect_language_tika_server"), "enhance_pdf_ocr")

		if "enhance_detect_language_tika_server" in self.config['plugins'] and "enhance_ocr_descew" in self.config['plugins']:
			if self.config['plugins'].index("enhance_ocr_descew") > self.config['plugins'].index("enhance_detect_language_tika_server"):
				# remove after
				self.config['plugins'].remove("enhance_ocr_descew")
				# add before
				self.config['plugins'].insert(self.config['plugins'].index("enhance_detect_language_tika_server"), "enhance_ocr_descew")

		# manual annotations should be found by by fulltext search too (automatic entity linking does by including the text or synonym)
		# so read befor generating the default search fields like _text_ or text_txt_languageX by enhance_multilingual 
		if "enhance_rdf_annotations_by_http_request" in self.config['plugins'] and "enhance_multilingual" in self.config['plugins']:
			if self.config['plugins'].index("enhance_rdf_annotations_by_http_request") > self.config['plugins'].index("enhance_multilingual"):
				# remove after
				self.config['plugins'].remove("enhance_rdf_annotations_by_http_request")
				# add before
				self.config['plugins'].insert(self.config['plugins'].index("enhance_multilingual"), "enhance_rdf_annotations_by_http_request")

		# if another exporter
		self.init_exporter()


	def is_plugin_blacklisted_for_contenttype(self, plugin, parameters, data):

		blacklisted = False

		# is there a content type yet?
		if 'content_type_ss' in data:
			content_types = data['content_type_ss']
		elif 'content_type_ss' in parameters:
			content_types = parameters['content_type_ss']
		else:
			content_types = None

		if not isinstance(content_types, list):
			content_types = [content_types]
			
		# if content type check the plugins' blacklists
		if content_types:
			
			for content_type in content_types:
	
				# directory where the plugins' blacklist are
				blacklistdir = '/etc/opensemanticsearch/blacklist/' + plugin + '/'
	
	
				filename = blacklistdir + 'blacklist-contenttype'
				if os.path.isfile(filename):
					if filter_blacklist.is_in_list(filename=filename, value=content_type):
						blacklisted = True
	
				if not blacklisted:
					filename = blacklistdir + 'blacklist-contenttype-prefix'
					if os.path.isfile(filename):
						if filter_blacklist.is_in_list(filename=filename, value=content_type, match="prefix"):
							blacklisted = True
				
				if not blacklisted:
					filename = blacklistdir + 'blacklist-contenttype-suffix'
					if os.path.isfile(filename):
						if filter_blacklist.is_in_list(filename=filename, value=content_type, match="suffix"):
							blacklisted = True
		
				if not blacklisted:
					filename = blacklistdir + 'blacklist-contenttype-regex'
					if os.path.isfile(filename):
						if filter_blacklist.is_in_list(filename=filename, value=content_type, match="regex"):
							blacklisted = True
	
	
				# check whitelists for plugin, if blacklisted but should not
				if blacklisted:
					filename = blacklistdir + 'whitelist-contenttype'
					if os.path.isfile(filename):
						if filter_blacklist.is_in_list(filename=filename, value=content_type):
							blacklisted = False
				
				if blacklisted:
					filename=blacklistdir + 'whitelist-contenttype-prefix'
					if os.path.isfile(filename):
						if filter_blacklist.is_in_list(filename=filename, value=content_type, match="prefix"):
							blacklisted = False
			
				if blacklisted:
					filename=blacklistdir + 'whitelist-contenttype-suffix'
					if os.path.isfile(filename):
						if filter_blacklist.is_in_list(filename=filename, value=content_type, match="suffix"):
							blacklisted = False
		
				if blacklisted:
					filename=blacklistdir + 'whitelist-contenttype-regex'
					if os.path.isfile(filename):
						if filter_blacklist.is_in_list(filename=filename, value=content_type, match="regex"):
							blacklisted = False
	

		return blacklisted
			
	
	def process (self, parameters={}, data={} ):

		if 'plugins' in parameters:
			plugins = parameters['plugins']
		else:
			plugins = self.config['plugins']


		for plugin in plugins:

			# mark plugin as runned			
			data['etl_' + plugin + '_b'] = True
			
			# if content_type / plugin combination blacklisted, continue with next plugin
			if self.is_plugin_blacklisted_for_contenttype(plugin, parameters, data):

				if self.verbose:
					print ( "Not starting plugin {} because this plugin is blacklisted for the contenttype".format(plugin) )

				# mark plugin as blacklisted			
				data['etl_' + plugin + '_blacklisted_b'] = True

				continue


			# start plugin
			if self.verbose:
				print ("Starting plugin {}".format(plugin))
			
			try:
				module = importlib.import_module(plugin)
				
				objectreference = getattr(module, plugin, False)

				if objectreference:	# if object oriented programming, run instance of object and call its "process" function
					enhancer = objectreference()
				
					parameters, data = enhancer.process(parameters=parameters, data=data)

				else:	# else call "process"-function
					functionreference = getattr(module, 'process', False)

					if functionreference:

						parameters, data = functionreference(parameters, data)
					
					else:
						sys.stderr.write( "Exception while data enrichment with plugin {}: Module implements wether object \"{}\" nor function \"process\"\n".format(plugin, plugin) )
	
			# if exception because user interrupted processing by keyboard, respect this and abbort
			except KeyboardInterrupt:
				raise KeyboardInterrupt

			# else dont break because fail of a plugin (maybe other plugins or data extraction will success), only error message
			except BaseException as e:

				#
				# Print error message and append errors to data
				# so we have a log and can see something went wrong within search engine and / or filter for that
				#
				
				try:

					sys.stderr.write( "Exception while data enrichment of {} with plugin {}: {}\n".format( parameters['id'], plugin, e ) )

					errormessage = "{}".format(e)
					
					if 'etl_error_txt' in data:
						data['etl_error_txt'].append(errormessage)
					else:
						data['etl_error_txt'] = [ errormessage ]
	
					if 'etl_error_plugins_ss' in data:
						data['etl_error_plugins_ss'].append(plugin)
					else:
						data['etl_error_plugins_ss'] = [ plugin ]
	
					data['etl_error_' + plugin + '_txt'] = errormessage

				except:
		
					sys.stderr.write( "Exception while generating error message for exception while processing plugin {} for file {}\n".format(plugin, parameters['id']) )

				if self.config['raise_pluginexception']:
					raise

	

			# Abort plugin chain if plugin set parameters['break'] to True
			# (used for example by blacklist or exclusion plugins)
			if 'break' in parameters:
				if parameters['break']:
					break



		# if processing aborted (f.e. by blacklist filter or file modification time did not change)
		abort = False
		if 'break' in parameters:
			if parameters['break']:
				abort = True

		if not abort:

			if 'export' in parameters:
				exporter = parameters['export']
			else:
				exporter = self.config['export']
	
			if exporter:
				# export results (data) to db/storage/index
				module = importlib.import_module(exporter)
				objectreference = getattr(module, exporter)
				self.exporter = objectreference(self.config)

				try:

					parameters, data = self.exporter.process(parameters=parameters, data=data)

				# if exception because user interrupted processing by keyboard, respect this and abbort
				except KeyboardInterrupt:
					raise KeyboardInterrupt
				except BaseException as e:
					sys.stderr.write( "Error while exporting to index or database: {}\n".format(parameters['id']) )
					raise e

		return parameters, data


	def commit(self):
		
		if self.verbose:
			print ("Commiting cached or open transactions to index")
		
		self.exporter.commit()
	

# append values (i.e. from an enhancer) to data structure
def append(data, facet, values):
	
		# if facet there yet, append/extend the values, else set values to facet
		if facet in data:

			# if new value(s) single value instead of list convert to list
			if not isinstance(values, list):
					values = [ values ]

			# if facet in data single value instead of list convert to list
			if not isinstance(data[facet], list):
				data[facet] = [ data[facet] ]

			# add new values to this list
			data[facet].extend(values)
		
			# dedupe data in facet
			data[facet] = list( set(data[facet]) )

			
			#if only one value, it has not to be a list
			if len(data[facet]) == 1:
				data[facet] = data[facet][0]

		else:
			data[facet] = values
	
