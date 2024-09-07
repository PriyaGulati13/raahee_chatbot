from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import mysql.connector
import logging
import re
from datetime import datetime, timedelta
from decimal import Decimal
from flask_mail import Mail, Message

app = Flask(__name__)

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USERNAME'] = 'yourmail@gmail.com'  
app.config['MAIL_PASSWORD'] = 'yourpassword'     
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
mail = Mail(app)

logging.basicConfig(level=logging.INFO)

db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'password',
    'database': 'name'
}

def send_session_email(action, user_info, therapist_info, session_info):
    subject_actions = {
        'booked': 'Session Booked',
        'cancelled': 'Session Cancelled',
        'rescheduled': 'Session Rescheduled'
    }
    
    subject = f"Therapy Session {subject_actions[action]}: {session_info['date']} at {session_info['time']}"
    
    body = f"""
    Dear {user_info['name']},

    This email is to confirm that your therapy session has been {action}.

    Session Details:
    - Date: {session_info['date']}
    - Time: {session_info['time']}
    - Duration: {session_info['duration']} minutes
    - {'New ' if action == 'rescheduled' else ''}Therapist: {therapist_info['name']}
    - Therapist Expertise: {therapist_info['area_of_expertise']}
    
    {'If you have any questions or need to make changes, please contact us.' if action != 'cancelled' else 'We hope to see you again soon.'}
    This is an auto-generated email. Please do not respond to this email.

    Best regards,
    Team Raahee
    """
    
    msg = Message(
        subject=subject,
        sender=app.config['MAIL_USERNAME'],
        recipients=[user_info['email']]
    )
    msg.body = body
    
    try:
        mail.send(msg)
        return True, "Email sent successfully"
    except Exception as e:
        logging.error(f"Failed to send email: {str(e)}")
        return False, f"Failed to send email: {str(e)}"
    
def get_user_info(user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT name, email FROM users WHERE id = %s", (user_id,))
    user_info = cursor.fetchone()
    cursor.close()
    conn.close()
    return user_info

def get_therapist_info(therapist_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT name, area_of_expertise FROM therapists WHERE id = %s", (therapist_id,))
    therapist_info = cursor.fetchone()
    cursor.close()
    conn.close()
    return therapist_info

def get_db_connection():
    return mysql.connector.connect(**db_config)

def check_user_exists(phone_number):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE phone_number = %s", (phone_number,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    return user[0] if user else None

def save_new_user(phone_number, name, age, email, pronoun, language):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (phone_number, name, age, email, pronoun, language)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (phone_number, name, age, email, pronoun, language))
    user_id = cursor.lastrowid
    conn.commit()
    cursor.close()
    conn.close()
    return user_id

def get_user_stage(session_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT stage FROM user_stages WHERE session_id = %s", (session_id,))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result[0] if result else 'start'

def set_user_stage(session_id, stage):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO user_stages (session_id, stage)
        VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE stage = %s
    """, (session_id, stage, stage))
    conn.commit()
    cursor.close()
    conn.close()

def set_temp_user_data(session_id, key, value):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO temp_user_data (session_id, data_key, data_value)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE data_value = %s
    """, (session_id, key, value, value))
    conn.commit()
    cursor.close()
    conn.close()

def get_temp_user_data(session_id, key):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT data_value FROM temp_user_data WHERE session_id = %s AND data_key = %s", (session_id, key))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result[0] if result else None

def get_therapists():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name, gender, fee, area_of_expertise FROM therapists")
    therapists = cursor.fetchall()
    cursor.close()
    conn.close()
    return therapists

def get_available_slots(therapist_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT id, DATE_FORMAT(start_time, '%Y-%m-%d %H:%i') as start_time 
        FROM therapist_slots 
        WHERE therapist_id = %s AND is_available = TRUE AND start_time > "2024-08-01 09:00"
        ORDER BY start_time
        LIMIT 5
    """, (therapist_id,))
    slots = cursor.fetchall()
    cursor.close()
    conn.close()
    return slots

def is_first_session(user_id, therapist_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) FROM therapist_sessions 
        WHERE user_id = %s AND therapist_id = %s
    """, (user_id, therapist_id))
    count = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    return count == 0

def book_session(user_id, therapist_id, slot_id, duration):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE therapist_slots 
            SET is_available = FALSE 
            WHERE id = %s
        """, (slot_id,))
        
        cursor.execute("""
            INSERT INTO therapist_sessions (user_id, therapist_id, slot_id, duration)
            VALUES (%s, %s, %s, %s)
        """, (user_id, therapist_id, slot_id, duration))
        
        conn.commit()
    except mysql.connector.Error as err:
        conn.rollback()
        logging.error(f"Error booking session: {err}")
        return False
    finally:
        cursor.close()
        conn.close()
    return True


def get_user_sessions(user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT ts.id, ts.therapist_id, t.name as therapist_name, DATE_FORMAT(s.start_time, '%Y-%m-%d %H:%i') as start_time, ts.duration
        FROM therapist_sessions ts
        JOIN therapists t ON ts.therapist_id = t.id
        JOIN therapist_slots s ON ts.slot_id = s.id
        WHERE ts.user_id = %s AND s.start_time > "2024-08-01 09:00"
        ORDER BY s.start_time
    """, (user_id,))
    sessions = cursor.fetchall()
    cursor.close()
    conn.close()
    return sessions

def reschedule_session(session_id, new_slot_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT slot_id FROM therapist_sessions WHERE id = %s", (session_id,))
        current_slot_id = cursor.fetchone()[0]

        cursor.execute("UPDATE therapist_slots SET is_available = TRUE WHERE id = %s", (current_slot_id,))

        cursor.execute("UPDATE therapist_slots SET is_available = FALSE WHERE id = %s", (new_slot_id,))

        cursor.execute("UPDATE therapist_sessions SET slot_id = %s WHERE id = %s", (new_slot_id, session_id))

        conn.commit()
        return True
    except mysql.connector.Error as err:
        conn.rollback()
        logging.error(f"Error rescheduling session: {err}")
        return False
    finally:
        cursor.close()
        conn.close()

def cancel_session(session_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT slot_id FROM therapist_sessions WHERE id = %s", (session_id,))
        slot_id = cursor.fetchone()[0]

        cursor.execute("UPDATE therapist_slots SET is_available = TRUE WHERE id = %s", (slot_id,))

        cursor.execute("DELETE FROM therapist_sessions WHERE id = %s", (session_id,))

        conn.commit()
        return True
    except mysql.connector.Error as err:
        conn.rollback()
        logging.error(f"Error cancelling session: {err}")
        return False
    finally:
        cursor.close()
        conn.close()

def get_session_fee(session_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.fee, ts.duration
        FROM therapist_sessions ts
        JOIN therapists t ON ts.therapist_id = t.id
        WHERE ts.id = %s
    """, (session_id,))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    if result:
        fee, duration = result
        return (fee * duration) / 60 
    return 0

def is_session_within_12_hours(session_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.start_time
        FROM therapist_sessions ts
        JOIN therapist_slots s ON ts.slot_id = s.id
        WHERE ts.id = %s
    """, (session_id,))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    if result:
        start_time = result[0]
        return abs(start_time - datetime.now()) < timedelta(hours=12)
    return False


def get_session_duration(session_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT duration FROM therapist_sessions WHERE id = %s", (session_id,))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result[0] if result else None

def set_initial_stage(session_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO user_stages (session_id, stage)
        VALUES (%s, 'start')
        ON DUPLICATE KEY UPDATE stage = 'start'
    """, (session_id,))
    conn.commit()
    cursor.close()
    conn.close()

def index(receiver):
    msg = Message(
        subject='Hello from the other side!', 
        sender='serenawarner08@gmail.com',  
        recipients=[receiver] 
    )
    msg.body = "Hey, sending you this email from my Flask app, let me know if it works."
    mail.send(msg)
    return "Message sent!"

@app.route('/wasms', methods=['POST'])
def webhook():
    incoming_msg = request.values.get('Body', '').strip().lower()
    session_id = request.values.get('From', '').replace("whatsapp:", "")
    
    resp = MessagingResponse()
    msg = resp.message()

    if incoming_msg in ['exit', 'quit', 'end']:
        msg.body("Thank you for using our service. Have a great day!")
        set_user_stage(session_id, 'start')
        return str(resp)
    
    if incoming_msg == 'back':
        msg.body("\nWhat would you like to do next?\n1. Book a new session\n2. View existing sessions\n3. Reschedule a session\n4. Cancel a session\n5. Rebook a session\n(Or type 'exit' to end the conversation)")
        set_user_stage(session_id, 'main_menu')
        return str(resp)

    user_stage = get_user_stage(session_id)

    if user_stage == 'start':
        set_user_stage(session_id, 'await_phone')
        msg.body("Welcome! Please enter your phone number. \n(Or type 'exit' to end the conversation)")
        return str(resp)

    elif user_stage == 'await_phone':
        if re.match(r'^\+?1?\d{9,15}$', incoming_msg):
            user_id = check_user_exists(incoming_msg)
            if user_id:
                set_temp_user_data(session_id, 'user_id', str(user_id))
                msg.body("Welcome back! What would you like to do?\n1. Book a new session\n2. View existing sessions\n3. Reschedule a session\n4. Cancel a session\n5. Rebook a session\n(Or type 'exit' to end the conversation)")
                set_user_stage(session_id, 'main_menu')
            else:
                set_temp_user_data(session_id, 'phone_number', incoming_msg)
                msg.body("New user! Please enter your name. \n(Or type 'exit' to end the conversation)")
                set_user_stage(session_id, 'await_name')
        else:
            msg.body("Invalid phone number format. Please try again. \n(Or type 'exit' to end the conversation)")

    elif user_stage == 'await_name':
        set_temp_user_data(session_id, 'name', incoming_msg)
        msg.body("Please enter your age. \n(Or type 'exit' to end the conversation)")
        set_user_stage(session_id, 'await_age')

    elif user_stage == 'await_age':
        if incoming_msg.isdigit() and 0 < int(incoming_msg) < 120:
            set_temp_user_data(session_id, 'age', incoming_msg)
            msg.body("Please enter your email address. \n(Or type 'exit' to end the conversation)")
            set_user_stage(session_id, 'await_email')
        else:
            msg.body("Invalid age. Please enter a number between 1 and 120. \n(Or type 'exit' to end the conversation)")

    elif user_stage == 'await_email':
        if re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', incoming_msg):
            set_temp_user_data(session_id, 'email', incoming_msg)
            msg.body("Please enter your preferred pronoun. \n(Or type 'exit' to end the conversation)")
            set_user_stage(session_id, 'await_pronoun')
        else:
            msg.body("Invalid email format. Please try again. \n(Or type 'exit' to end the conversation)")

    elif user_stage == 'await_pronoun':
        set_temp_user_data(session_id, 'pronoun', incoming_msg)
        msg.body("Please enter your preferred language. \n(Or type 'exit' to end the conversation)")
        set_user_stage(session_id, 'await_language')

    elif user_stage == 'await_language':
        set_temp_user_data(session_id, 'language', incoming_msg)
        phone_number = get_temp_user_data(session_id, 'phone_number')
        name = get_temp_user_data(session_id, 'name')
        age = get_temp_user_data(session_id, 'age')
        email = get_temp_user_data(session_id, 'email')
        pronoun = get_temp_user_data(session_id, 'pronoun')
        language = incoming_msg
        user_id = save_new_user(phone_number, name, age, email, pronoun, language)
        set_temp_user_data(session_id, 'user_id', str(user_id))
        msg.body("Thank you for providing your information. What would you like to do?\n1. Book a new session\n2. View existing sessions\n3. Reschedule a session\n4. Cancel a session\n5. Rebook a session\n(Or type 'exit' to end the conversation)")
        set_user_stage(session_id, 'main_menu')

    elif user_stage == 'main_menu':
        if incoming_msg == '1':
            therapists = get_therapists()
            therapist_list = "\n".join([f"{i+1}. {t['name']} - {t['gender']}, ${t['fee']}/hr, Expertise: {t['area_of_expertise']}" for i, t in enumerate(therapists)])
            msg.body(f"Here's a list of our therapists:\n{therapist_list}\nPlease select a therapist by entering the corresponding number. \n(Or type 'exit' to end the conversation) \n(Or type 'back' to return to the main menu)")
            set_temp_user_data(session_id, 'therapists', str(therapists))
            set_user_stage(session_id, 'select_therapist')
        elif incoming_msg == '2':
            user_id = int(get_temp_user_data(session_id, 'user_id'))
            sessions = get_user_sessions(user_id)
            if sessions:
                session_list = "\n".join([f"{i+1}. {s['therapist_name']} - {s['start_time']} ({s['duration']} minutes)" for i, s in enumerate(sessions)])
                msg.body(f"Your upcoming sessions:\n{session_list}")
            else:
                msg.body("You have no upcoming sessions.")
            msg.body("\nWhat would you like to do next?\n1. Book a new session\n2. View existing sessions\n3. Reschedule a session\n4. Cancel a session\n5. Rebook a session\n(Or type 'exit' to end the conversation)")
            set_user_stage(session_id, 'main_menu')
        elif incoming_msg in ['3', '4', '5']:
            user_id = int(get_temp_user_data(session_id, 'user_id'))
            sessions = get_user_sessions(user_id)
            if sessions:
                session_list = "\n".join([f"{i+1}. {s['therapist_name']} - {s['start_time']} ({s['duration']} minutes)" for i, s in enumerate(sessions)])
                msg.body(f"Your upcoming sessions:\n{session_list}\nPlease select a session by entering the corresponding number. (Or type 'exit' to end the conversation)")
                set_temp_user_data(session_id, 'sessions', str(sessions))
                if incoming_msg == '3':
                    set_user_stage(session_id, 'reschedule_session_select')
                elif incoming_msg == '4':
                    set_user_stage(session_id, 'cancel_session_select')
                else:  # '5'
                    set_user_stage(session_id, 'rebook_session_select')
            else:
                msg.body("You have no upcoming sessions to modify.")
                msg.body("\nWhat would you like to do?\n1. Book a new session\n2. View existing sessions\n3. Reschedule a session\n4. Cancel a session\n5. Rebook a session\n(Or type 'exit' to end the conversation)")
                set_user_stage(session_id, 'main_menu')
        else:
            msg.body("Invalid selection. Please enter a number corresponding to an option. \n(Or type 'exit' to end the conversation) \n(Or type 'back' to return to the main menu)")

    elif user_stage == 'select_therapist':
        therapists = eval(get_temp_user_data(session_id, 'therapists'))
        if incoming_msg.isdigit() and 0 < int(incoming_msg) <= len(therapists):
            selected_therapist = therapists[int(incoming_msg) - 1]
            set_temp_user_data(session_id, 'selected_therapist_id', str(selected_therapist['id']))
            
            user_id = int(get_temp_user_data(session_id, 'user_id'))
            if is_first_session(user_id, selected_therapist['id']):
                msg.body("As this is your first session with this therapist, would you like to book a free 15-minute trial? (Yes/No) \n(Or type 'exit' to end the conversation) \n(Or type 'back' to return to the main menu)")
                set_user_stage(session_id, 'confirm_trial')
            else:
                slots = get_available_slots(selected_therapist['id'])
                slot_list = "\n".join([f"{i+1}. {s['start_time']}" for i, s in enumerate(slots)])
                msg.body(f"Please select an available slot:\n{slot_list}\n(Or type 'exit' to end the conversation) \n(Or type 'back' to return to the main menu)")
                set_temp_user_data(session_id, 'available_slots', str(slots))
                set_temp_user_data(session_id, 'is_trial', 'false')
                set_user_stage(session_id, 'select_slot')
        else:
            msg.body("Invalid selection. Please enter a number corresponding to a therapist. \n(Or type 'exit' to end the conversation) \n(Or type 'back' to return to the main menu)")

    elif user_stage == 'confirm_trial':
        if incoming_msg == 'yes':
            therapist_id = int(get_temp_user_data(session_id, 'selected_therapist_id'))
            slots = get_available_slots(therapist_id)
            slot_list = "\n".join([f"{i+1}. {s['start_time']}" for i, s in enumerate(slots)])
            msg.body(f"Great! Please select an available slot for your 15-minute trial:\n{slot_list}\n(Or type 'exit' to end the conversation) \n(Or type 'back' to return to the main menu)")
            set_temp_user_data(session_id, 'available_slots', str(slots))
            set_temp_user_data(session_id, 'is_trial', 'true')
            set_user_stage(session_id, 'select_slot')
        elif incoming_msg == 'no':
            therapist_id = int(get_temp_user_data(session_id, 'selected_therapist_id'))
            slots = get_available_slots(therapist_id)
            slot_list = "\n".join([f"{i+1}. {s['start_time']}" for i, s in enumerate(slots)])
            msg.body(f"Okay, let's book a regular session. Please select an available slot:\n{slot_list}\n(Or type 'exit' to end the conversation) \n(Or type 'back' to return to the main menu)")
            set_temp_user_data(session_id, 'available_slots', str(slots))
            set_temp_user_data(session_id, 'is_trial', 'false')
            set_user_stage(session_id, 'select_slot')
        else:
            msg.body("Invalid input. Please answer 'Yes' or 'No'. \n(Or type 'exit' to end the conversation) \n(Or type 'back' to return to the main menu)")

    elif user_stage == 'select_slot':
        slots = eval(get_temp_user_data(session_id, 'available_slots'))
        if incoming_msg.isdigit() and 0 < int(incoming_msg) <= len(slots):
            selected_slot = slots[int(incoming_msg) - 1]
            set_temp_user_data(session_id, 'selected_slot', str(selected_slot))
            is_trial = get_temp_user_data(session_id, 'is_trial') == 'true'
            
            user_id = int(get_temp_user_data(session_id, 'user_id'))
            therapist_id = int(get_temp_user_data(session_id, 'selected_therapist_id'))
            
            if is_trial:
                if book_session(user_id, therapist_id, selected_slot['id'], 15):
                    user_info = get_user_info(user_id)
                    therapist_info = get_therapist_info(therapist_id)
                    session_info = {
                        'date': selected_slot['start_time'].split()[0],
                        'time': selected_slot['start_time'].split()[1],
                        'duration': 15
                    }
                    
                    email_sent, email_message = send_session_email('booked', user_info, therapist_info, session_info)
                    
                    if email_sent:
                        msg.body(f"Great! Your 15-minute trial session has been booked for {selected_slot['start_time']}. We look forward to seeing you! An email confirmation has been sent to {user_info['email']}.")
                    else:
                        msg.body(f"Great! Your 15-minute trial session has been booked for {selected_slot['start_time']}. We look forward to seeing you! However, we couldn't send an email confirmation due to a technical issue.")
                else:
                    msg.body("I'm sorry, there was an error booking your trial session. Please try again later or contact our support team.")
            else:
                therapist = next(t for t in eval(get_temp_user_data(session_id, 'therapists')) if t['id'] == therapist_id)
                fee = therapist['fee']
                msg.body(f"You've selected a 60-minute session at {selected_slot['start_time']}. The fee for this session is ${fee}.\n\nDo you want to proceed with the payment? (Yes/No)\n(Or type 'exit' to end the conversation) \n(Or type 'back' to return to the main menu)")
                set_user_stage(session_id, 'confirm_payment')
            
            msg.body("\nWhat would you like to do next?\n1. Book a new session\n2. View existing sessions\n3. Reschedule a session\n4. Cancel a session\n5. Rebook a session\n(Or type 'exit' to end the conversation) \n(Or type 'back' to return to the main menu)")
            set_user_stage(session_id, 'main_menu')

        else:
            msg.body("Invalid selection. Please enter a number corresponding to an available slot. \n(Or type 'exit' to end the conversation) \n(Or type 'back' to return to the main menu)")

    elif user_stage == 'confirm_payment':
        if incoming_msg.lower() == 'yes':
            user_id = int(get_temp_user_data(session_id, 'user_id'))
            therapist_id = int(get_temp_user_data(session_id, 'selected_therapist_id'))
            selected_slot = eval(get_temp_user_data(session_id, 'selected_slot'))
            
            if book_session(user_id, therapist_id, selected_slot['id'], 60):
                user_info = get_user_info(user_id)
                therapist_info = get_therapist_info(therapist_id)
                session_info = {
                    'date': selected_slot['start_time'].split()[0],
                    'time': selected_slot['start_time'].split()[1],
                    'duration': 60
                }
                
                email_sent, email_message = send_session_email('booked', user_info, therapist_info, session_info)

                if email_sent:
                    msg.body(f"Payment successful! Your 60-minute session has been booked for {selected_slot['start_time']}. We look forward to seeing you! An email confirmation has been sent to {user_info['email']}.")
                else:
                    msg.body(f"Payment successful! Your 60-minute session has been booked for {selected_slot['start_time']}. We look forward to seeing you! However, we couldn't send an email confirmation due to a technical issue.")
            else:
                msg.body("I'm sorry, there was an error processing your payment and booking your session. Please try again later or contact our support team.")
        elif incoming_msg.lower() == 'no':
            msg.body(f"No problem. Your session has not been booked and no payment has been processed.")
        else:
            msg.body("Invalid input. Please answer 'Yes' or 'No'. \n(Or type 'exit' to end the conversation) \n(Or type 'back' to return to the main menu)")
            return str(resp)
        
        msg.body("\nWhat would you like to do next?\n1. Book a new session\n2. View existing sessions\n3. Reschedule a session\n4. Cancel a session\n5. Rebook a session\n(Or type 'exit' to end the conversation)")
        set_user_stage(session_id, 'main_menu')
        return str(resp)


    elif user_stage == 'confirm_reschedule_fee':
        if incoming_msg == 'yes':
            selected_session_id = int(get_temp_user_data(session_id, 'selected_session_id'))
            therapist_id = int(get_temp_user_data(session_id, 'selected_therapist_id'))
            slots = get_available_slots(therapist_id)
            slot_list = "\n".join([f"{i+1}. {s['start_time']}" for i, s in enumerate(slots)])
            msg.body(f"Please select a new slot:\n{slot_list}\n(Or type 'exit' to end the conversation) \n(Or type 'back' to return to the main menu)")
            set_temp_user_data(session_id, 'available_slots', str(slots))
            set_user_stage(session_id, 'reschedule_select_slot')
        elif incoming_msg == 'no':
            msg.body("Rescheduling cancelled. No changes have been made to your session.")
            msg.body("\nWhat would you like to do next?\n1. Book a new session\n2. View existing sessions\n3. Reschedule a session\n4. Cancel a session\n5. Rebook a session\n(Or type 'exit' to end the conversation)")
            set_user_stage(session_id, 'main_menu')
        else:
            msg.body("Invalid input. Please answer 'Yes' or 'No'. \n(Or type 'exit' to end the conversation) \n(Or type 'back' to return to the main menu)")

    elif user_stage == 'reschedule_session_select':
        sessions = eval(get_temp_user_data(session_id, 'sessions'))
        if incoming_msg.isdigit() and 0 < int(incoming_msg) <= len(sessions):
            selected_session = sessions[int(incoming_msg) - 1]
            set_temp_user_data(session_id, 'selected_session_id', str(selected_session['id']))
            set_temp_user_data(session_id, 'selected_therapist_id', str(selected_session['therapist_id']))
            
            if is_session_within_12_hours(selected_session['id']):
                fee = get_session_fee(selected_session['id'])
                msg.body(f"This session is within 12 hours. Rescheduling will incur a fee of ${fee:.2f}. Do you want to proceed? (Yes/No)\n(Or type 'exit' to end the conversation) \n(Or type 'back' to return to the main menu)" ) 
                set_user_stage(session_id, 'confirm_reschedule_fee')
            else:
                therapist_id = selected_session['therapist_id']
                slots = get_available_slots(therapist_id)
                slot_list = "\n".join([f"{i+1}. {s['start_time']}" for i, s in enumerate(slots)])
                msg.body(f"Please select a new slot:\n{slot_list}\n(Or type 'exit' to end the conversation) \n(Or type 'back' to return to the main menu)")
                set_temp_user_data(session_id, 'available_slots', str(slots))
                set_user_stage(session_id, 'reschedule_select_slot')
        else:
            msg.body("Invalid selection. Please enter a number corresponding to a session. \n(Or type 'exit' to end the conversation) \n(Or type 'back' to return to the main menu)")

    elif user_stage == 'reschedule_select_slot':
        slots = eval(get_temp_user_data(session_id, 'available_slots'))
        if incoming_msg.isdigit() and 0 < int(incoming_msg) <= len(slots):
            new_slot = slots[int(incoming_msg) - 1]
            session_id_to_reschedule = int(get_temp_user_data(session_id, 'selected_session_id'))
            if reschedule_session(session_id_to_reschedule, new_slot['id']):
                user_id = int(get_temp_user_data(session_id, 'user_id'))
                therapist_id = int(get_temp_user_data(session_id, 'selected_therapist_id'))
                user_info = get_user_info(user_id)
                therapist_info = get_therapist_info(therapist_id)
                session_info = {
                    'date': new_slot['start_time'].split()[0],
                    'time': new_slot['start_time'].split()[1],
                    'duration': get_session_duration(session_id_to_reschedule)
                }
                
                email_sent, email_message = send_session_email('rescheduled', user_info, therapist_info, session_info)
                
                if email_sent:
                    msg.body(f"Your session has been rescheduled to {new_slot['start_time']}. An email confirmation has been sent to {user_info['email']}.")
                else:
                    msg.body(f"Your session has been rescheduled to {new_slot['start_time']}. However, we couldn't send an email confirmation due to a technical issue.")
            else:
                msg.body("There was an error rescheduling your session. Please try again later or contact support.")
            
            msg.body("\nWhat would you like to do next?\n1. Book a new session\n2. View existing sessions\n3. Reschedule a session\n4. Cancel a session\n5. Rebook a session\n(Or type 'exit' to end the conversation)")
            set_user_stage(session_id, 'main_menu')
        else:
            msg.body("Invalid selection. Please enter a number corresponding to an available slot. \n(Or type 'exit' to end the conversation) \n(Or type 'back' to return to the main menu)")

    elif user_stage == 'cancel_session_select':
        sessions = eval(get_temp_user_data(session_id, 'sessions'))
        if incoming_msg.isdigit() and 0 < int(incoming_msg) <= len(sessions):
            selected_session = sessions[int(incoming_msg) - 1]
            set_temp_user_data(session_id, 'selected_session_id', str(selected_session['id']))
            
            if is_session_within_12_hours(selected_session['id']):
                fee = get_session_fee(selected_session['id'])
                msg.body(f"This session is within 12 hours. Cancelling will incur a fee of ${fee:.2f}. Do you want to proceed? (Yes/No)\n(Or type 'exit' to end the conversation) \n(Or type 'back' to return to the main menu)")
                set_user_stage(session_id, 'confirm_cancel_fee')
            else:
                msg.body("Are you sure you want to cancel this session? (Yes/No)\n(Or type 'exit' to end the conversation) \n(Or type 'back' to return to the main menu)")
                set_user_stage(session_id, 'confirm_cancel')
        else:
            msg.body("Invalid selection. Please enter a number corresponding to a session. \n(Or type 'exit' to end the conversation) \n(Or type 'back' to return to the main menu)")

    elif user_stage in ['confirm_cancel_fee', 'confirm_cancel']:
        if incoming_msg == 'yes':
            session_id_to_cancel = int(get_temp_user_data(session_id, 'selected_session_id'))
            if cancel_session(session_id_to_cancel):
                user_id = int(get_temp_user_data(session_id, 'user_id'))
                therapist_id = int(get_temp_user_data(session_id, 'selected_therapist_id'))
                user_info = get_user_info(user_id)
                therapist_info = get_therapist_info(therapist_id)
                session_info = {
                    'date': 'N/A',  
                    'time': 'N/A', 
                    'duration': get_session_duration(session_id_to_cancel)
                }
                
                email_sent, email_message = send_session_email('cancelled', user_info, therapist_info, session_info)
                
                if email_sent:
                    msg.body(f"Your session has been cancelled. An email confirmation has been sent to {user_info['email']}.")
                else:
                    msg.body("Your session has been cancelled. However, we couldn't send an email confirmation due to a technical issue.")
                
                if user_stage == 'confirm_cancel_fee':
                    fee = get_session_fee(session_id_to_cancel)
                    msg.body(f"A cancellation fee of ${fee:.2f} has been charged.")
            else:
                msg.body("There was an error cancelling your session. Please try again later or contact support.")
        elif incoming_msg == 'no':
            msg.body("Cancellation aborted. Your session remains scheduled.")
        else:
            msg.body("Invalid input. Please answer 'Yes' or 'No'. \n(Or type 'exit' to end the conversation) \n(Or type 'back' to return to the main menu)")
            return str(resp)
        
        msg.body("\nWhat would you like to do next?\n1. Book a new session\n2. View existing sessions\n3. Reschedule a session\n4. Cancel a session\n5. Rebook a session\n(Or type 'exit' to end the conversation)")
        set_user_stage(session_id, 'main_menu')

    elif user_stage == 'rebook_session_select':
        sessions = eval(get_temp_user_data(session_id, 'sessions'))
        if incoming_msg.isdigit() and 0 < int(incoming_msg) <= len(sessions):
            selected_session = sessions[int(incoming_msg) - 1]
            set_temp_user_data(session_id, 'selected_session_id', str(selected_session['id']))
            set_temp_user_data(session_id, 'selected_therapist_id', str(selected_session['therapist_id']))
            
            therapist_id = selected_session['therapist_id']
            slots = get_available_slots(therapist_id)
            slot_list = "\n".join([f"{i+1}. {s['start_time']}" for i, s in enumerate(slots)])
            msg.body(f"Please select a new slot for rebooking:\n{slot_list}\n(Or type 'exit' to end the conversation) \n(Or type 'back' to return to the main menu)")
            set_temp_user_data(session_id, 'available_slots', str(slots))
            set_user_stage(session_id, 'rebook_select_slot')
        else:
            msg.body("Invalid selection. Please enter a number corresponding to a session. \n(Or type 'exit' to end the conversation) \n(Or type 'back' to return to the main menu)")

    elif user_stage == 'rebook_select_slot':
        slots = eval(get_temp_user_data(session_id, 'available_slots'))
        if incoming_msg.isdigit() and 0 < int(incoming_msg) <= len(slots):
            new_slot = slots[int(incoming_msg) - 1]
            old_session_id = int(get_temp_user_data(session_id, 'selected_session_id'))
            
            if cancel_session(old_session_id):
                
                user_id = int(get_temp_user_data(session_id, 'user_id'))
                therapist_id = int(get_temp_user_data(session_id, 'selected_therapist_id'))
                duration = get_session_duration(old_session_id)
                
                if book_session(user_id, therapist_id, new_slot['id'], duration):
                    msg.body(f"Your session has been rebooked for {new_slot['start_time']}.")
                else:
                    msg.body("There was an error rebooking your session. Please try again later or contact support.")
            else:
                msg.body("There was an error cancelling your old session. Rebooking failed. Please try again later or contact support.")
            
            msg.body("\nWhat would you like to do next?\n1. Book a new session\n2. View existing sessions\n3. Reschedule a session\n4. Cancel a session\n5. Rebook a session\n(Or type 'exit' to end the conversation)")
            set_user_stage(session_id, 'main_menu')
        else:
            msg.body("Invalid selection. Please enter a number corresponding to an available slot. \n(Or type 'exit' to end the conversation) \n(Or type 'back' to return to the main menu)")

    else:
        msg.body("I'm sorry, I didn't understand that. Please try again or type 'restart' to start over. \n(Or type 'exit' to end the conversation) \n(Or type 'back' to return to the main menu)")
        set_user_stage(session_id, 'start')

    return str(resp)

if __name__ == '__main__':
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT session_id FROM user_stages")
    sessions = cursor.fetchall()
    for session in sessions:
        set_initial_stage(session[0])
    cursor.close()
    conn.close()

    app.run(host='0.0.0.0', port=5001, debug=True)