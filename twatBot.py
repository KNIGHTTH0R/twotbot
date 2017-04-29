#! /usr/bin/env python3

import sys
import signal
import argparse
import pprint
import json
from time import sleep, localtime, strftime
from datetime import datetime
from random import randint
# Reddit imports:
import praw
import pdb
import re
import os
# Twitter imports:
import tweepy

# global variables
twatbot_abs_dir = os.path.dirname(os.path.abspath(__file__)) #<-- absolute path to twatbot directory
# paths to files
path_scrp_dmp = None
path_queries = None
path_promos = None
path_log = None
# twitter
p_lines = []
p_length = 0
q_lines = []
q_length = 0
api = None
# reddit
reddit = None
reddit_subkeys = None


# record certain events in log.txt
def log(s):
    t = strftime("%Y%b%d %H:%M:%S", localtime()) + " " + s

    with open(path_log, 'a') as l:
        l.write(t + "\n")
        
    # also print truncated log to screen
    p = t[:90] + (t[90:] and '..')
    print(p)

def authReddit():
    global reddit
    global reddit_subkeys
    global path_scp_dmp
    global path_queries
    global path_promos
    global path_log
    
    # get paths to filesk TODO use them for seperate jobs
    #path_scrp_dmp = os.path.join(twatbot_abs_dir, 'red_scrape_dump.txt')
    #path_queries =  os.path.join(twatbot_abs_dir, 'red_queries.txt')
    #path_promos =  os.path.join(twatbot_abs_dir, 'red_promos.txt')
    path_log =  os.path.join(twatbot_abs_dir, 'red_log.txt')

    print("Authenticating...")

    reddit = praw.Reddit('twatBot')

    log("Authenticated as: " + str(reddit.user.me()));

    # get subreddits, e.g.: androidapps+androiddev+all
    with open('red_subkey_pairs.json') as json_data:
        subkeys_parsed = json.load(json_data)
        reddit_subkeys = subkeys_parsed['sub_key_pairs']

def buildRedDumpLine(submission):
    return (datetime.fromtimestamp(int(submission.created)).strftime("%b%d %H:%M")
            + "SUBM_URL" + str(submission.url)
            + "SUBM_TXT" + submission.selftext.replace("\n", "") + "\n")

def parseRedDumpLine(dl):
    # parse scrape dump file, seperate tweet ids from screen names
    a1 = dl.split('SUBM_URL')
    a2 = a1[1].split('SUBM_TXT')
    # [time, twt_id, scrn_name, twt_txt]
    return [a1[0], a2[0], a2[1]]

def processSubmission(submission):
    # open dump file in read mode
    with open('red_scrape_dump.txt', 'r') as f:
        scrp_lines = f.readlines()

        # if submission already scraped, then return
        if any(str(submission.id) in s for s in scrp_lines):
            return 0

    # otherwise append to red_scrape_dump.txt
    with open('red_scrape_dump.txt', 'a') as f:
        f.write(buildRedDumpLine(submission))
        return 1

def getRandRedPromo():
    with open('red_promos.txt') as f:
        rp_lines = f.readlines()
        f_length = sum(1 for _ in rp_lines)
        return rp_lines[randint(0, f_length - 1)]
        
def replyReddit():
     # open dump file in read mode
    with open('red_scrape_dump.txt', 'r') as f:
        post_lines = f.readlines()

        # reply to lines not marked with prefix '-'
        for post in post_lines:
            pd = parseRedDumpLine(post)

            if pd[0][0] == '-':
                continue
            # get submission from submission.id stored in scrape dump
            submission = reddit.submission(url=pd[1])
            # reply with random promotion
            try:
                submission.reply(getRandRedPromo())
                log('Replied: ' + pd[1])
                
                # wait for 45-75 secs to evade spamming flags
                sleep(randint(45, 75))
            except praw.exceptions.ClientException as e:
                log("Error: " + e.message)

def scrapeReddit(scrape_limit, r_new, r_top, r_hot, r_ris):
    
    def scrape_log(i, k):
        log("Scraped: {total} submissions ({new} new) in {subs}".format(
            total=str(i), 
            new=str(k),
            subs=subredstr))

    # search each subreddit combo for new submissions matching its associated keywords
    for subkey in reddit_subkeys:
        i = 0 # total submissions scraped
        k = 0 # new submissions scraped
        
        subredstr = subkey["subreddits"]
        subreddits = reddit.subreddit(subredstr)
        
        # search new, hot, or rising categories?
        category = None
        if r_new:
            category = subreddits.new(limit=int(scrape_limit))
            print("Searching new " + str(subreddits))
        elif r_top:
            category = subreddits.top(limit=int(scrape_limit))
            print("Searching top " + str(subreddits))
        elif r_hot:
            category = subreddits.hot(limit=int(scrape_limit))
            print("Searching hot " + str(subreddits))
        elif r_ris:
            category = subreddits.rising(limit=int(scrape_limit))
            print("Searching rising " + str(subreddits))
        else:
            print("Which category would you like to scrape? [-n|-t|-H|-r]")
            sys.exit(1)
        
        # indefinitely monitor new submissions with: subreddit.stream.submissions()
        for submission in category:
            done = False
            # process any submission with title/text fitting and/or/not keywords
            tit_txt = submission.title.lower() + submission.selftext.lower()

            # must not contain any NOT keywords
            for kw in subkey['keywords_not']:
                if kw in tit_txt:
                    done = True
            if done:
                continue

            # must contain all AND keywords
            for kw in subkey['keywords_and']:
                if not kw in tit_txt:
                    done = True
            if done:
                continue

            # must contain at least one OR keyword
            for kw in subkey['keywords_or']:
                if kw in tit_txt:
                    break

            k += processSubmission(submission)
            i += 1                    
        scrape_log(i, k)


# get authentication credentials and tweepy api object
def authTwitter(job):
    
    global path_scrp_dmp
    global path_queries
    global path_promos
    global path_log
    global p_lines
    global p_length
    global q_lines
    global q_length
    global api
    
    # get correct paths to files for current job
    if job:
        cred_path = os.path.join(twatbot_abs_dir, job + '/credentials.txt')    
        path_scrp_dmp = os.path.join(twatbot_abs_dir, job + '/twit_scrape_dump.txt')
        path_queries = os.path.join(twatbot_abs_dir, job + '/twit_queries.txt')
        path_promos = os.path.join(twatbot_abs_dir, job + '/twit_promos.txt')
        path_log = os.path.join(twatbot_abs_dir, job + '/log.txt')
    else:
        cred_path = os.path.join(twatbot_abs_dir, 'credentials.txt')
        path_scrp_dmp = os.path.join(twatbot_abs_dir, 'twit_scrape_dump.txt')
        path_queries = os.path.join(twatbot_abs_dir, 'twit_queries.txt')
        path_promos = os.path.join(twatbot_abs_dir, 'twit_promos.txt')
        path_log = os.path.join(twatbot_abs_dir, 'log.txt')
    
    # get authorization credentials from credentials file
    with open(cred_path, 'r') as creds:
        
        # init empty array to store credentials
        cred_lines = [None] * 4
        
        # strip end of line characters and any trailing spaces, tabs off credential lines
        cred_lines_raw = creds.readlines()
        for i in range(len(cred_lines_raw)):
            cred_lines[i] = (cred_lines_raw[i].strip())

        print("Authenticating...")        
        # authenticate and get reference to api
        auth = tweepy.OAuthHandler(cred_lines[0], cred_lines[1])
        auth.set_access_token(cred_lines[2], cred_lines[3])
        api = tweepy.API(auth)
    
    # ensure authentication was successful
    try:
        log("Authenticated as: " + api.me().screen_name)
    except tweepy.TweepError as e:
        log("Failed Twitter auth: " + e.reason)
        sys.exit(1)

    #  load promo lines (tweets) from text file
    with open(path_promos, 'r') as promoFile:
        p_lines = promoFile.readlines()

    # load queries from text file
    with open(path_queries, 'r') as queryFile:
        q_lines = queryFile.readlines()

    # get number of promotional tweets and queries
    p_length = sum(1 for _ in p_lines)
    q_length = sum(1 for _ in q_lines)


def getRandPromo():
    return p_lines[randint(0, p_length - 1)]


# update status with random promotional tweet
def updateStatus():
    promo = getRandPromo()
    try:
        # skip blank lines
        if promo != '\n':
            # send tweet
            api.update_status(promo)
            log(" Tweeted: " + promo)
    except tweepy.TweepError as e:
        log(e.reason)


def folTweeter(scrn_name):
    try:
        # follow, if not already
        friends = api.get_user(scrn_name).following
        if not friends:
            api.create_friendship(scrn_name)
        else:
            log("Already following: " + scrn_name)
            return
    except tweepy.TweepError as e:
        log("Error: " + e.reason)
        return

    log("Followed: " + scrn_name)
    
def spamOP(twt_id, scrn_name):
    # reply to op with random spam
    spamPost = getRandPromo()
    api.update_status('@' + scrn_name + ' ' + spamPost, twt_id)

    log("Spammed: " + scrn_name)
    
    # wait 45-75 seconds between spam tweets
    wt = randint(45, 75)
    print("waiting " + str(wt) + "s...")
    sleep(wt)


def replyToTweet(twt_id, scrn_name):
    try:
        # favorite tweet, will throw error if tweet already favorited so as to avoid double spamming
        api.create_favorite(twt_id)
        log("Favorited: " + scrn_name + " [" + twt_id + "]")
        
        # try spamming op with random promo line
        spamOP(twt_id, scrn_name)
        return 1
            
    except tweepy.TweepError as e:
        if '139' in e.reason:
            log("Skipped " + twt_id + ": Already favorited/spammed " + scrn_name + " - " + e.reason)
            return 0
        if '136' in e.reason:
            log("Skipped " + twt_id + ": Blocked from favoriting " + scrn_name + "'s tweets - " + e.reason)
            return 0
        elif '226' in e.reason:
            log(e.reason)
            log("Automated activity detected: waiting for next 15m window...")
            # wait for next 15m window to throw anti-spam bots off the scent
            sleep(randint(900, 1000))
            return 2
        elif ('326' in e.reason) or ('261' in e.reason) or ('cannot POST' in e.reason):
            log(e.reason)
            log("Terminal API Error returned: exiting, see log.txt for details.")
            return 3

def directMessageTweet(scrn_name):
    try:
        # send direct message to tweeter
        api.send_direct_message(screen_name=scrn_name, text=getRandPromo())

    except tweepy.TweepError as e:
        log("Error: " + e.reason)
        return
    
    log("Direct Messaged: " + scrn_name)
    
def buildDumpLine(tweet):
    return (tweet.created_at.strftime("%b%d %H:%M")
                + "TWT_ID" + str(tweet.id)
                + "SCRN_NAME" + tweet.user.screen_name
                + "TWT_TXT" + tweet.text.replace("\n", "") + "\n")
    
def parseDumpLine(dl):
    # parse scrape dump file, seperate tweet ids from screen names
    a1 = dl.split('TWT_ID')
    a2 = a1[1].split('SCRN_NAME')
    a3 = a2[1].split('TWT_TXT')
    # [time, twt_id, scrn_name, twt_txt]
    return [a1[0], a2[0], a3[0], a3[1]]
   

def processTweet(tweet, pro, fol, dm):

    scrn_name = tweet.user.screen_name
    
    # open dump file in read mode
    with open(path_scrp_dmp, 'r') as f:
        scrp_lines = f.readlines()

        # if tweet already scraped, then return
        if any(str(tweet.id) in s for s in scrp_lines):
            return 0

    # otherwise append to twit_scrape_dump.txt    
    new_line = buildDumpLine(tweet)
    with open(path_scrp_dmp, 'a') as f:
        f.write(new_line)
    
    # follow op, if not already following
    if fol and not tweet.user.following:
        folTweeter(scrn_name)

    # favorite and respond to op's tweet
    if pro:
        replyToTweet(tweet.id, scrn_name)
        
    # direct message op
    if dm:
        directMessageTweet(scrn_name)
    
    return 1 # return count of new tweets added to twit_scrape_dump.txt


# continuously scrape for tweets matching all queries
def scrapeTwitter(con, eng, fol, pro, dm):
   
    def scrape_log(i, k):
        log(("Scraped: {total} tweets ({new} new) found with: {query}\n".format(
        total=str(i), 
        new=str(k), 
        query=query.replace("\n", ""))))
    
    print("Scraping...")
   
    for query in q_lines:
        c = None
        if eng:
            c = tweepy.Cursor(api.search, q=query, lang='en').items()
        else:
            c = tweepy.Cursor(api.search, q=query).items()
        i = 0 # total tweets scraped
        k = 0 # new tweets scraped
        while True:
            try:
                # prompt user to continue scraping after 50 results
                if (not con and i%51 == 50):
                    query_trunc = query[:20] + (query[20:] and '..')
                    keep_going = input("{num} results scraped for {srch}, keep going? (Y/n):".format(num=str(i), srch=query_trunc))
                    if (keep_going != "Y"):
                        raise StopIteration()
                # process next tweet
                k += processTweet(c.next(), pro, fol, dm)                    
                i += 1
            except tweepy.TweepError as e:
                if '403' in e.reason:
                    log("403 not found: check your queries for validity")
                    sys.exit(1)
                scrape_log(i, k)
                log("Reached API window limit: taking 15min smoke break..." + e.reason)
                # wait for next request window to continue
                sleep(60 * 15)
                continue
            except StopIteration:
                scrape_log(i, k)
                break


# get command line arguments and execute appropriate functions
def main(argv):
    # for logging purposes
    start_time = datetime.now()
    reply_count = 0
    
    def log_run_time():
        log("Total run time: " + str(datetime.now() - start_time))
    
    # catch SIGINTs and KeyboardInterrupts
    def signal_handler(signal, frame):
        if args.t_pro:
            log("Replied to {rep} tweets.".format(rep=str(reply_count)))
        log("Current job terminated: received KeyboardInterrupt kill signal.")
        log_run_time()
        sys.exit(0)
    # set SIGNINT listener to catch kill signals
    signal.signal(signal.SIGINT, signal_handler)

    parser = argparse.ArgumentParser(description="Beep, boop.. I'm a social media promotion bot - Let's get spammy!")

    subparsers = parser.add_subparsers(help='platforms', dest='platform')
    
    # Twitter arguments
    twit_parser = subparsers.add_parser('twitter', help='Twitter: scrape for queries, promote to results')
    twit_parser.add_argument('-j', '--job', dest='JOB_DIR', help="choose job to run by specifying job's relative directory")
    twit_parser.add_argument('-u', '--update-status', action='store_true', dest='t_upd', help='update status with random promo from twit_promos.txt')
    group_scrape = twit_parser.add_argument_group('query')
    group_scrape.add_argument('-s', '--scrape', action='store_true', dest='t_scr', help='scrape for tweets matching queries in twit_queries.txt')
    group_scrape.add_argument('-c', '--continuous', action='store_true', dest='t_con', help='scape continuously - suppress prompt to continue after 50 results per query')
    group_scrape.add_argument('-e', '--english', action='store_true', dest='t_eng', help='return only tweets written in English')
    
    group_promote = twit_parser.add_argument_group('spam')
    group_promote.add_argument('-f', '--follow', action='store_true', dest='t_fol', help='follow original tweeters in twit_scrape_dump.txt')
    group_promote.add_argument('-p', '--promote', action='store_true', dest='t_pro', help='favorite tweets and reply to tweeters in twit_scrape_dump.txt with random promo from twit_promos.txt')
    group_promote.add_argument('-d', '--direct-message', action='store_true', dest='t_dm', help='direct message tweeters in twit_scrape_dump.txt with random promo from twit_promos.txt')
    
    # Reddit arguments
    reddit_parser = subparsers.add_parser('reddit', help='Reddit: scrape subreddits, promote to results')
    reddit_parser.add_argument('-s', '--scrape', dest='N', help='scrape subreddits in subreddits.txt for keywords in red_keywords.txt; N = number of posts to scrape')
    categories = reddit_parser.add_mutually_exclusive_group()
    categories.add_argument('-n', '--new', action='store_true', dest='r_new', help='scrape new posts')
    categories.add_argument('-t', '--top', action='store_true', dest='r_top', help='scrape top posts')
    categories.add_argument('-H', '--hot', action='store_true', dest='r_hot', help='scrape hot posts')
    categories.add_argument('-r', '--rising', action='store_true', dest='r_ris', help='scrape rising posts')
    reddit_parser.add_argument('-p', '--promote', action='store_true', dest='r_pro', help='promote to posts in red_scrape_dump.txt not marked with a "-" prefix')

    executed = 0 # catches any command/args that fall through below tree
    args = parser.parse_args()
    
    # twitter handler
    if args.platform == 'twitter':
        # get authentication credentials and api
        authTwitter(args.JOB_DIR)

        # update status
        if args.t_upd:
            updateStatus()
            executed = 1

        # scrape twitter for all queries and favorite, follow, and/or promote OPs
        if args.t_scr:
            scrapeTwitter(args.t_con, args.t_eng, args.t_fol, args.t_pro, args.t_dm)
            executed = 1
        else: # otherwise promote to all entries in scrape_dump file
            # get scrape dump lines
            f = open(path_scrp_dmp, "r")
            scrp_lines = f.readlines()
            f.close()
            
            for i in range(len(scrp_lines)):
                pd = parseDumpLine(scrp_lines[i])

                # ignore lines beginning with '-'
                if pd[0][0] == '-':
                    continue
                    
                twt_id = pd[1]
                scrn_name = pd[2]
                
                if args.t_fol:
                    folTweeter(scrn_name)
                
                if args.t_pro:
                    ret_code = replyToTweet(twt_id, scrn_name)
                    # continue if no error code returned
                    if ret_code is 1:
                        reply_count += ret_code
                    elif ret_code is 2: # automation detected
                        pass #already slept it off, do nothing
                    elif ret_code is 3: # serious error returned, terminate activity
                        log("Prematurely terminating job: replied to {rep} tweets.".format(rep=str(reply_count)))
                        log_run_time()
                        sys.exit(1)
                        
                    # prefix spammed scape dump lines with '-'
                    scrp_lines[i] = '-' + scrp_lines[i]
                    f = open(path_scrp_dmp, "w")
                    f.writelines(scrp_lines)
                    f.close()
                    
                if args.t_dm:
                    directMessageTweet(scrn_name)
            
            log("Job done. Replied to {rep} tweets.".format(rep=str(reply_count)))
            log_run_time()
                
            executed = 1

    # reddit handler
    if args.platform == 'reddit':
        authReddit()

        if args.N:
            scrapeReddit(args.N, args.r_new, args.r_top, args.r_hot, args.r_ris)
            executed = 1

        if args.r_pro:
            replyReddit()
            executed = 1
    
    if not executed:
        log("Unknown Execution Error")
        parser.print_help()
        sys.exit(1)

            
            
# so main() isn't executed if file is imported
if __name__ == "__main__":
    # remove first script name argument
    main(sys.argv[1:])
    
    
    
