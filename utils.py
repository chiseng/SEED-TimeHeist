import json
import os
from datetime import datetime
import pytz

max_questions = 12
hr_to_start = 14
min_to_start = 15

def init_config(group_number):
	config = {}
	group_number = int(group_number)
	config['group_number'] = group_number
	config['score'] = 0
	config['trivia_progress'] = 0
	config['next_question'] = 0
	config['member_count'] = 0
	config['chat_id_list'] = []
	config['current_solved'] = []

	with open(f'configs/{group_number}.json', 'w') as outfile:
		json.dump(config, outfile)

def write_to_config(group_number, **kwargs):
	with open(f'configs/{group_number}.json','r') as iofile:
		config_load = json.load(iofile)
	for k,v in kwargs.items():
		if isinstance(config_load[k], list):
			if isinstance(v,list):
				config_load[k] = v
				continue
			config_load[k].append(v)
			continue
		config_load[k] = v
	with open(f'configs/{group_number}.json', 'w') as outfile:
		json.dump(config_load, outfile)

def read_config(group_number):
	if not os.path.isfile(f'configs/{group_number}.json'):
		return False
	with open(f'configs/{group_number}.json','r') as iofile:
		config_load = json.load(iofile)	
	return config_load



def auth_member(group_number, chat_id) -> int:
	#Make sure the member has not already subscribed
	config_load = read_config(group_number)
	print(config_load)
	if not config_load:
		return False

	trivia_progress = config_load.get('trivia_progress', 0)
	if trivia_progress == -1: # If the game has ended, set the trivia progress back to restart the trivia
		write_to_config(group_number, trivia_progress=0)
		config_load = read_config(group_number)

	chat_id_list = config_load.get('chat_id_list', [])
	if chat_id in chat_id_list:
		return False

	else:
		next_question = 'None'
		if config_load['next_question'] != 0:
			next_question = config_load['next_question']
		write_to_config(group_number, chat_id_list=chat_id)
		return next_question

def end_game(group_number:int, handle:str) -> bool:
	config_load = read_config(group_number)
		# Reset all values for config
	if config_load['trivia_progress'] == -1 :
		write_to_config(group_number, 
			trivia_progress=-1,
			next_question=0,
			member_count=0,
			chat_id_list=[],
			)
		return -1
	else:
		return -2

def get_trivia_question(quiz_list, group_number): # We only look at next_question here
	current_time = datetime.now(pytz.timezone('Asia/Singapore'))
	total_now = current_time.hour * 3600 + current_time.minute * 60
	start = hr_to_start * 3600 + min_to_start * 60
	if total_now < start:
		return "Early"
	config_load = read_config(group_number)
	next_question = config_load['next_question']
	trivia_question = ''
	if next_question == max_questions or config_load['trivia_progress'] == -1:
		return 'Finished'

	if not len(config_load['chat_id_list']) or not config_load: # game ended or no members or wrong group
		return trivia_question


	trivia_question = "Here is the first trivia question!\n\n" + quiz_list[0]
	write_to_config(group_number, next_question=next_question+1)
	
	if next_question != 0: # Update the progress
		trivia_question = quiz_list[next_question]
		next_question += 1
		write_to_config(group_number, next_question=next_question)

	return trivia_question

def update_progress(group_number, question_number): # We only look at trivia_progress here
	config_load = read_config(group_number)
	progress = config_load['trivia_progress'] + 1
	if progress == max_questions:
		score = config_load['score'] + 1
		write_to_config(group_number, 
			next_question=0, 
			trivia_progress=-1, 
			score=score
			)
		return 1
	score = config_load['score'] + 1
	write_to_config(group_number, trivia_progress=progress, score=score, current_solved=question_number)

def check_solved(group_number, question_number):
	config_load = read_config(group_number)
	if question_number in config_load['current_solved']:
		return False
	return True

def get_group_number(message):
	try:
		group_number = int(message.data)
		return group_number
	except ValueError:
		return False

def leave_helper(group_number, chat_id):
	config_load = read_config(group_number)
	chat_id_list = config_load['chat_id_list']
	idx = chat_id_list.index(chat_id)
	chat_id_list.pop(idx)
	write_to_config(group_number, chat_id_list=chat_id_list)

def get_scores(number_of_groups):
	string = ''
	print(number_of_groups)
	for i in range(1, number_of_groups + 1):
		config_load = read_config(i)
		string += str(i) + ": " + str(config_load['score'])
		string += "\n"
	return string


