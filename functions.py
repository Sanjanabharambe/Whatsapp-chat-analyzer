import re
from collections import Counter

import pandas as pd
import seaborn as sns
import streamlit as st
from collections import Counter
import matplotlib.pyplot as plt
from nltk.sentiment.vader import SentimentIntensityAnalyzer
from transformers import pipeline
import nltk
import urlextract
import emoji
from wordcloud import WordCloud

nltk.download('vader_lexicon') 

# VADER Sentiment Analysis
def sentiment_analysis_vader(df):
    # Initialize VADER sentiment analyzer
    sia = SentimentIntensityAnalyzer()

    # Apply VADER sentiment analysis on each message
    df['sentiment'] = df['Message'].apply(lambda msg: sia.polarity_scores(msg))
    
    # Extract the 'compound' sentiment score
    df['sentiment_score'] = df['sentiment'].apply(lambda sentiment: sentiment['compound'])
    
    # Label the sentiment: Positive, Neutral, or Negative
    df['sentiment_label'] = df['sentiment_score'].apply(
        lambda score: 'Positive' if score > 0.05 else ('Negative' if score < -0.05 else 'Neutral')
    )
    
    return df

# Function to calculate response time between consecutive messages
def calculate_response_time(df):
    df['DateTime'] = pd.to_datetime(df['Date'] + ' ' + df['Time(U)'])
    df['Next_User'] = df['User'].shift(-1)
    df['Next_DateTime'] = df['DateTime'].shift(-1)
    df['Response_Time'] = (df['Next_DateTime'] - df['DateTime']).dt.total_seconds() / 60  # in minutes
    df = df[df['User'] != df['Next_User']]  # Remove consecutive messages from the same user
    return df

# Compute average response time by user
def average_response_time_by_user(df):
    return df.groupby('User')['Response_Time'].mean().reset_index()

# Compute average response time between pairs of users
def average_response_time_between_users(df):
    """Compute average response time between pairs of users."""
    
    # Ensure proper ordering of the DataFrame by DateTime
    df['DateTime'] = pd.to_datetime(df['Date'] + ' ' + df['Time(U)'])
    df = df.sort_values('DateTime')
    
    # Generate the next user for each message in the conversation
    df['Next_User'] = df['User'].shift(-1)
    
    # Only keep rows where there is an actual 'Next_User' (i.e., skip last row)
    df = df.dropna(subset=['Next_User'])
    
    # Calculate response time (time difference between consecutive messages by different users)
    df['Response_Time'] = (df['DateTime'].shift(-1) - df['DateTime']).dt.total_seconds() / 60  # Convert to minutes

    # Create a new column for the pair of users (to handle both directions, like A->B and B->A)
    df['Pair'] = df.apply(lambda row: tuple(sorted([row['User'], row['Next_User']])), axis=1)

    # Calculate average response time for each pair of users
    pair_avg_response_time = df.groupby('Pair')['Response_Time'].mean().reset_index()

    # Create a matrix with user pairs as rows and columns
    user_list = df['User'].unique()
    response_matrix = pd.DataFrame(index=user_list, columns=user_list, data=0.0)

    # Populate the matrix with average response times
    for _, row in pair_avg_response_time.iterrows():
        user1, user2 = row['Pair']
        response_matrix.loc[user1, user2] = row['Response_Time']
        response_matrix.loc[user2, user1] = row['Response_Time']  # response time is symmetric

    print("Response Matrix:\n", response_matrix)  # Debugging line to check matrix
    return response_matrix


# Function to plot heatmap of response times between users
def plot_response_time_between_users(df):
    response_matrix = average_response_time_between_users(df)
    fig, ax = plt.subplots(figsize=(10, 8))
    
    # Check if response_matrix is empty or not
    if response_matrix.empty:
        st.error("No data available for response time between users.")
        return

    sns.heatmap(response_matrix.astype(float), annot=True, cmap="Blues", fmt=".2f", 
                cbar_kws={'label': 'Response Time (minutes)'}, ax=ax)
    ax.set_title("Average Response Time Between Users")
    ax.set_ylabel('User')
    ax.set_xlabel('User')
    plt.xticks(rotation=90)
    plt.tight_layout()
    st.pyplot(fig)

# Function to plot average response time by user
def plot_average_response_time_by_user(df):
    user_avg_response_time = average_response_time_by_user(df)
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.bar(user_avg_response_time['User'], user_avg_response_time['Response_Time'], color='skyblue')
    ax.set_xlabel("User")
    ax.set_ylabel("Average Response Time (minutes)")
    ax.set_title("Average Response Time by User")
    plt.xticks(rotation=90)
    plt.tight_layout()
    st.pyplot(fig)


def generateDataFrame(file):
    data = file.read().decode("utf-8")
    data = data.replace('\u202f', ' ')
    data = data.replace('\n', ' ')
    dt_format = '\d{1,2}/\d{1,2}/\d{2,4},\s\d{1,2}:\d{2}\s?(?:AM\s|PM\s|am\s|pm\s)?-\s'
    msgs = re.split(dt_format, data)[1:]
    date_times = re.findall(dt_format, data)
    date = []
    time = []
    for dt in date_times:
        date.append(re.search('\d{1,2}/\d{1,2}/\d{2,4}', dt).group())
        time.append(re.search('\d{1,2}:\d{2}\s?(?:AM|PM|am|pm)?', dt).group())
    users = []
    message = []
    for m in msgs:
        s = re.split('([\w\W]+?):\s', m)
        if (len(s) < 3):
            users.append("Notifications")
            message.append(s[0])
        else:
            users.append(s[1])
            message.append(s[2])
    df = pd.DataFrame(list(zip(date, time, users, message)), columns=["Date", "Time(U)", "User", "Message"])
    return df


def getUsers(df):
    users = df['User'].unique().tolist()
    users.sort()
    users.remove('Notifications')
    users.insert(0, 'Everyone')
    return users


def PreProcess(df,dayf):
    df['Date'] = pd.to_datetime(df['Date'], dayfirst=dayf)
    df['Time'] = pd.to_datetime(df['Time(U)']).dt.time
    df['year'] = df['Date'].apply(lambda x: int(str(x)[:4]))
    df['month'] = df['Date'].apply(lambda x: int(str(x)[5:7]))
    df['date'] = df['Date'].apply(lambda x: int(str(x)[8:10]))
    df['day'] = df['Date'].apply(lambda x: x.day_name())
    df['hour'] = df['Time'].apply(lambda x: int(str(x)[:2]))
    df['month_name'] = df['Date'].apply(lambda x: x.month_name())
    return df


def getStats(df):
    media = df[df['Message'] == "<Media omitted> "]
    media_cnt = media.shape[0]
    df.drop(media.index, inplace=True)
    deleted_msgs = df[df['Message'] == "This message was deleted "]
    deleted_msgs_cnt = deleted_msgs.shape[0]
    df.drop(deleted_msgs.index, inplace=True)
    temp = df[df['User'] == 'Notifications']
    df.drop(temp.index, inplace=True)
    print("h4")
    extractor = urlextract.URLExtract()
    print("h3")
    links = []
    for msg in df['Message']:
        x = extractor.find_urls(msg)
        if x:
            links.extend(x)
    links_cnt = len(links)
    word_list = []
    for msg in df['Message']:
        word_list.extend(msg.split())
    word_count = len(word_list)
    msg_count = df.shape[0]
    return df, media_cnt, deleted_msgs_cnt, links_cnt, word_count, msg_count


def getEmoji(df):
    emojis = []
    for message in df['Message']:
        emojis.extend([c for c in message if c in emoji.EMOJI_DATA])
    return pd.DataFrame(Counter(emojis).most_common(len(Counter(emojis))))


def getMonthlyTimeline(df):

    df.columns = df.columns.str.strip()
    df=df.reset_index()
    timeline = df.groupby(['year', 'month']).count()['Message'].reset_index()
    time = []
    for i in range(timeline.shape[0]):
        time.append(str(timeline['month'][i]) + "-" + str(timeline['year'][i]))
    timeline['time'] = time
    return timeline


def MostCommonWords(df):
    f = open('stop_hinglish.txt')
    stop_words = f.read()
    f.close()
    words = []
    for message in df['Message']:
        for word in message.lower().split():
            if word not in stop_words:
                words.append(word)
    return pd.DataFrame(Counter(words).most_common(20))

def dailytimeline(df):
    df['taarek'] = df['Date']
    daily_timeline = df.groupby('taarek').count()['Message'].reset_index()
    fig, ax = plt.subplots()
    #ax.figure(figsize=(100, 80))
    ax.plot(daily_timeline['taarek'], daily_timeline['Message'])
    ax.set_ylabel("Messages Sent")
    st.title('Daily Timeline')
    st.pyplot(fig)

def WeekAct(df):
    x = df['day'].value_counts()
    fig, ax = plt.subplots()
    ax.bar(x.index, x.values)
    ax.set_xlabel("Days")
    ax.set_ylabel("Message Sent")
    plt.xticks(rotation='vertical')
    st.pyplot(fig)

def MonthAct(df):
    x = df['month_name'].value_counts()
    fig, ax = plt.subplots()
    ax.bar(x.index, x.values)
    ax.set_xlabel("Months")
    ax.set_ylabel("Message Sent")
    plt.xticks(rotation='vertical')
    st.pyplot(fig)

def activity_heatmap(df):
    period = []
    for hour in df[['day', 'hour']]['hour']:
        if hour == 23:
            period.append(str(hour) + "-" + str('00'))
        elif hour == 0:
            period.append(str('00') + "-" + str(hour + 1))
        else:
            period.append(str(hour) + "-" + str(hour + 1))

    df['period'] = period
    user_heatmap = df.pivot_table(index='day', columns='period', values='Message', aggfunc='count').fillna(0)
    return user_heatmap
def create_wordcloud(df):

    f = open('stop_hinglish.txt', 'r')
    stop_words = f.read()
    f.close()
    def remove_stop_words(message):
        y = []
        for word in message.lower().split():
            if word not in stop_words:
                y.append(word)
        return " ".join(y)

    wc = WordCloud(width=500,height=500,min_font_size=10,background_color='white')
    df['Message'] = df['Message'].apply(remove_stop_words)
    df_wc = wc.generate(df['Message'].str.cat(sep=" "))
    return df_wc
