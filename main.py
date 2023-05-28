import telebot
import configparser
from utils import *
import hashlib
import random
import re
import time
import os
from collections import defaultdict
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from telebot import types, TeleBot
import copy
from telebot.handler_backends import ContinueHandling
import datetime
import schedule, threading
import logging


config = configparser.ConfigParser()
config.read('config.conf')
BOT_TOKEN = config['Bot Token']['bot_token']
master_id = int(config['Master']['master_id'])
start_message = config['Start']['start_message']
trivia_message = config['Trivia']['message']
manual_message = config['Manual']['message']
trivia_interval = 11

bot = telebot.TeleBot(BOT_TOKEN)
member_mapping = {} # chat id: number
group_mapping = defaultdict(list) # number: chatid
group_timer_channel = {} # group number: start time
groups_started = {}
groups_ended = {}
quiz_list = list(config['Questions'].values())
answer_list = list(config['Answers'].values())

groups = [1,2,3,4,5,6,7,8,9,10]

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Create config directory if not present
if not os.path.isdir('configs'):
	os.mkdir('configs')

'''
Group methods
'''
	
def join_handler(message):
	group_number = get_group_number(message)
	try:
		group_number = int(message.data)
	except:
		bot.send_message(message.chat.id, "Error: Enter a squad to start. Try again", parse_mode="Markdown")
		return
	copy_mapping = copy.deepcopy(group_mapping) # Here in case of race conditions
	for item in copy_mapping.values():
		for val in item:
			if val == message.from_user.id:
				bot.answer_callback_query(message.id, 'Do not attempt to join multiple squads', cache_time=30)
				return
	retval = auth_member(group_number, message.from_user.id)
	member_mapping[message.from_user.id] = group_number
	group_mapping[group_number].append(message.from_user.id)
	if retval == -1:
		bot.answer_callback_query(message.id, 'Squad does not exist!')
	elif retval:
		bot.answer_callback_query(message.id, f'Successfully joined group {group_number}!')
		logger.info("User %s joined group %s.", message.from_user.username, group_number)
		if retval != "None":
			bot.send_message(message.from_user.id, f"Welcome! Here's the current question!\n\n{quiz_list[retval - 1]}", parse_mode='Markdown')
		
	else:
		bot.answer_callback_query(message.id, 'Failed to join the group')

	del copy_mapping

def group_number_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    
    for i in range(0, len(groups), 2):
        buttons = [
            types.InlineKeyboardButton(text=str(groups[i]), callback_data=str(groups[i]))
        ]
        if i + 1 < len(groups):
            buttons.append(types.InlineKeyboardButton(text=str(groups[i + 1]), callback_data=str(groups[i + 1])))
        
        markup.add(*buttons)
    
    return markup

''' 
Trivia methods
'''

def trivia_handler(message):	
	start_time = time.time()
	group_number = member_mapping.get(message.chat.id)
	if group_number == None:
		bot.send_message(message.chat.id, "You're not part of a squad!!", parse_mode="Markdown")
		return
	if message.text.upper() != "START" and (group_number not in group_timer_channel):
		bot.send_message(message.chat.id, "`Returning..`", parse_mode="Markdown")
		return
	# Make sure the chatter isn't in a group that has already started the trivia

	if group_number not in group_timer_channel:
		group_timer_channel[group_number] = round(start_time, -1)
		bot.send_message(message.chat.id, "`Started the timer!`", parse_mode="Markdown")

	# Start trivia only at a certain time

	question = get_trivia_question(quiz_list, group_number) # first question
	if question == "Early":
		bot.send_message(message.chat.id,"`The Time Maniac is currently in a different dimension. Return later to challenge him..`", parse_mode="Markdown")
		return
	if group_number in groups_started:
		bot.send_message(message.chat.id, "`Do not challenge the Time Maniac twice!`", parse_mode="Markdown")
		return

	if question == '':
		bot.send_message(message.chat.id, "Error retrieving next question. You may have\n\n1: Received all the questions or\n2: Not joined a squad", parse_mode="Markdown")
	else:
		if question == 'Finished':
			bot.send_message(message.chat.id, "Error retrieving next question. You may have\n\n1: Ended the game or\n2: Finished the trivia", parse_mode='Markdown')
			return
		groups_started[group_number] = True
		for id in group_mapping[group_number]:
			bot.send_message(id, trivia_message, parse_mode='Markdown')
			bot.send_message(id, question, parse_mode="Markdown")

		schedule.every(trivia_interval).minutes.do(trivia_looper, group_number).tag(str(group_number), str(message.chat.id))
	

def trivia_looper(group_number):
	question = get_trivia_question(quiz_list, group_number)
	if question != 'Finished':
		for id in group_mapping[group_number]:
			bot.send_message(id, question, parse_mode="Markdown")
	else:
		return schedule.CancelJob


def solve_handler(message, question_number):
	group_number = member_mapping.get(message.chat.id)
	if group_number is None or group_number not in group_mapping:
		bot.send_message(message.chat.id, "Error!\n\n1. Please start the trivia before solving or\n2.Join a group\n\nTry again", parse_mode='Markdown')
		return


	checked = check_solved(group_number, question_number)
	if not checked:
		bot.send_message(message.chat.id, "`!! SOLVING A SOLVED QUESTION IS ILLEGAL !!`", parse_mode='Markdown')
		return

	answer = answer_list[question_number - 1]
	user_input = message.text.lower()

	if question_number == 6:
		wrong = user_input not in ['footstep', 'footsteps']
	elif question_number == 10:
		wrong = user_input not in ['pencil lead', 'lead']
	else:
		wrong = answer.lower() != user_input

	if wrong:
		flavour = ['Time to reconsider your answer..', 'Maybe a solution for a different timeline..',"Doesn't seem right..",'The Time Maniac will not be pleased..']
		rand = random.choice(flavour)
		bot.send_message(message.chat.id, rand, parse_mode='Markdown')
		return


	success = "`You've outsmarted the Time Maniac!`"
	bot.send_message(message.chat.id, success, parse_mode='Markdown')

	for id in group_mapping[group_number]:
		if id != message.chat.id:
			bot.send_message(id, f"Question {question_number} solved! The answer is: {message.text}", parse_mode='Markdown')


	retval = update_progress(group_number, question_number)
	if retval:
		bot.send_message(id, f"`Congratulations, you've beaten the Time Maniac!`", parse_mode='Markdown')

def question_number_handler(message):
	question_number = message.text.split(" ")[-1]
	try:
		question_number = int(question_number)
	except ValueError:
		bot.send_message(message.chat.id, "Enter a puzzle number to solve. E.g. /solve 5", parse_mode='Markdown')
		return
	if not (1 <= question_number <= len(answer_list)):
		bot.send_message(message.chat.id, "Question number does not exist", parse_mode='Markdown')
		return
	sent_msg = bot.send_message(message.chat.id, '`Prove your worth:`', parse_mode="Markdown")
	bot.register_next_step_handler(sent_msg, lambda m: solve_handler(m,question_number))

'''
hints
'''
def hint_handler(message, group_number):
	group_number = member_mapping[message.chat.id]
	bot.send_message(message.chat.id, '`Help will be sent to your squad shortly, but due to time irregularities the message may have gone to your squad members. Please check with them`', parse_mode='Markdown')
	sent_msg = bot.send_message(master_id, f'Group {group_number} is stuck. "{message.text}"', parse_mode='Markdown')

#Reply to message and send back to the sender
def respond_hint(message, group_number):
	list_of_ids = group_mapping.get(group_number, [])
	if not len(list_of_ids):
		bot.send_message(message.chat.id, f"No one in the team", parse_mode='Markdown')
		return
	player_id = random.choice(list_of_ids)
	bot.send_message(player_id, f"`A message from the timekeeper: {message.text}`", parse_mode='Markdown')

'''
end game
'''
# Ends the game for the team, returns score and time taken to the game master
def end_handler(message):
	group_number = member_mapping.get(message.chat.id)
	group_ended = groups_ended.get(group_number)
	if message.text.upper() != "END" and group_ended == None:
		bot.send_message(message.chat.id, "Returning..", parse_mode="Markdown")
		return
	end = time.time()
	retval = end_game(group_number, message.from_user.username)	
	if retval == -1:
		for id in group_mapping[group_number]:
			bot.send_message(id, '`You proudly display your hard earned proof of outsmarting the Time Maniac, forcing the timekeeper to re-sync you to your timeline.`', parse_mode="Markdown")
		bot.send_message(master_id, f'Squad {group_number} completed all challenges.', parse_mode="Markdown")
		group_mapping[group_number] = [] #Clears group mapping so that members can rejoin the group if the accidentally press END
		if group_ended:
			return

	if groups_started[group_number] and group_ended == None:
		time_taken = end - int(group_timer_channel[group_number])
		h = int(time_taken/3600)
		m = int((time_taken - h*3600)/60)
		s = int(time_taken - h*3600 - m*60)
		parsed_time_taken = f'{h}h:{m}m:{s}s'
		# Change this to send to game master
		bot.send_message(master_id, f'Squad {group_number} took {parsed_time_taken}', parse_mode="Markdown")
		bot.send_message(message.chat.id, '`Congratulations Chronomonitors, you have successfully foiled the plans of the Time Maniac with your combined efforts! Please head back to Trehaus for mission debrief & refreshments. ⏳`', parse_mode="Markdown")
		for id in group_mapping[group_number]:
			bot.send_message(id, '`You may continue solving the challenges to prove your worth to the timekeeper! Click /end again when you have finished all challenges`', parse_mode="Markdown")
		groups_ended[group_number] = True
	else:
		bot.send_message(message.chat.id, "Error!! You're not part of a squad or have ended multiple times before completing the challenges")


def broadcast_handler(message):
	for id_list in group_mapping.values():
		bot.send_message(id_list[0], message.text)
	return

'''
Bot commands
'''

@bot.message_handler(commands=['start', 'welcome'], chat_types=["private", "group"])
def start(message):
	text = start_message
	bot.send_message(message.chat.id, start_message, parse_mode="Markdown")


@bot.message_handler(commands=['join'], chat_types=["private", "group"])
def member_join(message):
	bot.send_message(message.chat.id, '`Select your Chrono Squad`', parse_mode="Markdown", reply_markup=group_number_keyboard())

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
	join_handler(call)


# Make it such that randy gets the hints and randy gets to send hints back
@bot.message_handler(commands=['help'], chat_types=["private", "group"])
def request_hints(message):
	group_number = member_mapping.get(message.chat.id)
	timing = group_timer_channel.get(group_number)
	group_list = group_mapping.get(group_number)
	if (group_number or timing) == None or not len(group_list):
		bot.send_message(message.chat.id, "Error!!\n\n1.You're not part of a squad or\n2.You have not started the challenge", parse_mode="Markdown")
		return
	text = "What are you stuck with?"
	sent_msg = bot.send_message(message.chat.id, text, parse_mode="Markdown")
	bot.register_next_step_handler(sent_msg, lambda m: hint_handler(m, group_number))

@bot.message_handler(commands=['challenge'], chat_types=["private", "group"])
def start_trivia(message):
	group_number = member_mapping.get(message.chat.id)
	started = group_timer_channel.get(group_number)
	if started == None:
		sent_msg = bot.send_message(message.chat.id, '`!! WARNING: DOING THIS STARTS THE TIMER FOR YOUR SQUAD !! Enter START to challenge or anything else to return`', parse_mode="Markdown")
		bot.register_next_step_handler(sent_msg, trivia_handler)
		return ContinueHandling()
	trivia_handler(message)

@bot.message_handler(commands=['end'], chat_types=["private", "group"])
def endgame(message):
	group_number = member_mapping.get(message.chat.id)
	if group_number not in group_timer_channel or group_number == None:
		bot.send_message(message.chat.id, "Error!! You did not start the challenge or you're not part of a squad", parse_mode="Markdown")
		return
	ended = groups_ended.get(group_number)
	if ended == None:
		message = bot.send_message(message.chat.id, "`!! WARNING: THIS CANNOT BE REVERSED !! Enter END to end. Any other response to return`", parse_mode="Markdown")
		bot.register_next_step_handler(message, end_handler)
		return ContinueHandling()
	end_handler(message)

@bot.message_handler(commands=['manual'], chat_types=["private", "group"])
def manual(message):
	bot.send_message(message.chat.id, manual_message, parse_mode="Markdown")

@bot.message_handler(commands=['solve'], chat_types=["private", "group"])
def solver(message):
	if message.chat.id not in member_mapping.keys():
		bot.send_message(message.chat.id, 'Join a squad before trying to solve.', parse_mode="Markdown")
		return

	question_number_handler(message)

@bot.message_handler(commands=['respond'])
def handle_respond(message):
	if message.chat.id != master_id:
		bot.send_message(message.chat.id, "`Contact the timekeeper for a reward`", parse_mode="Markdown")
		return
	try:
		group_number = int(message.text.split(" ")[-1])
	except ValueError:
		bot.send_message(message.chat.id, "Enter a group number")
		return
	sent_msg = bot.send_message(message.chat.id, 'Enter response', parse_mode="Markdown")
	bot.register_next_step_handler(sent_msg, lambda m: respond_hint(m, group_number))


@bot.message_handler(commands=['leave'], chat_types=["private", "group"])
def leave_group(message):
	group_number = member_mapping.get(message.chat.id)
	group_list = group_mapping.get(group_number)
	if (group_list == None) or group_number == None:
		bot.send_message(message.chat.id, "Error!! You're not in a squad!", parse_mode="Markdown")
		return
	leave_helper(group_number, message.chat.id)
	idx = group_mapping[group_number].index(message.chat.id)
	member_mapping[message.chat.id] = 0
	group_mapping[group_number].pop(idx)
	logger.info("User %s left group %s.", message.from_user.username, group_number)
	bot.send_message(message.chat.id, "`You have left the squad!`", parse_mode="Markdown")

@bot.message_handler(commands=['scores'], chat_types=["private", "group"])
def score_handler(message):
	if message.chat.id != master_id:
		bot.send_message(message.chat.id, "`Contact the timekeeper for a reward`", parse_mode="Markdown")
		return
	scores = get_scores(len(groups))
	bot.send_message(message.chat.id, scores)

@bot.message_handler(commands=['broadcast'], chat_types=["private", "group"])
def broadcast(message):
	msg = bot.send_message(message.chat.id, "Enter your message")	
	bot.register_next_step_handler(msg, broadcast_handler)

# for i in range(1,len(groups) + 1):
# 	init_config(i)

threading.Thread(target=bot.infinity_polling, name='bot_infinity_polling', daemon=True).start()

while True:
    schedule.run_pending()
    time.sleep(1)
