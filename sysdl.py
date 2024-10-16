#!/usr/bin/env python3
import sched
import time
from datetime import datetime
import threading
import cherrypy
import json
import os
from pvrecorder import PvRecorder
#import pyaudio
import wave
import struct  # Utilisé pour convertir la liste en format binaire


record_seconds = 5400
#RECORD_SECONDS = 10
#RECORD_SECONDS = 5400
cherrypy.config.update({'log.screen': False,
                        'log.access_file': 'access.log',
                        'log.error_file': 'error.log'})

# Le planificateur et les données des tâches
scheduler = sched.scheduler(time.time, time.sleep)
tasks = []
task_history = []
task_id_counter = 0
fmt = "%a-%d/%m/%Y-%H:%M:%S"
fmt_output = "%a-%d%m%Y-%H:%M:%S"
fmt_calender = "%Y-%m-%dT%H:%M"
style = """<style>
           html {zoom: 300%;}
           body {
               background-color: black;
               color: white;
               font-family: monospace, monospace;
           } 
           a {
               color: cyan;
           }
           h2 {
               color: #ffA060;
           }
           h3 {
               color: hotpink;
           }
           table, th, td {
               border:1px solid white;
           }
           label {
               display: block;
               font: 1rem 'Fira Sans', sans-serif;
           }
           input, label {
               margin: 0.4rem 0;
           }
           </style>"""

TASK_FILE = "tasks.json"
FORMAT = 'int16'        # Format des données (16 bits)
CHANNELS = 1            # Nombre de canaux (mono)
RATE = 16000            # Taux d'échantillonnage (16 kHz)
CHUNK = 1024            # Taille des blocs de données


# Sauvegarder les tâches futures dans un fichier JSON
def save_tasks():
    with open(TASK_FILE, "w") as f:
        json.dump(tasks, f)

# Charger les tâches à partir d'un fichier JSON
def load_tasks():
    global task_id_counter
    if os.path.exists(TASK_FILE):
        with open(TASK_FILE, "r") as f:
            loaded_tasks = json.load(f)
            for task in loaded_tasks:
                task_time_remaining = task['time'] - time.time()
                if task_time_remaining > 0:
                    # Restaurer la tâche dans le scheduler
                    scheduler.enter(task_time_remaining, 1, task_action, argument=(task['id'], task['description']))
                    tasks.append(task)
                    task_id_counter = max(task_id_counter, task['id'] + 1)

# Démarrer le planificateur dans un thread
def run_scheduler():
    while True:
        scheduler.run(blocking=False)
        time.sleep(1)  # Eviter une boucle de scrutation intense

scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
scheduler_thread.start()

# Fonction de la tâche à exécuter
def task_action(task_id, description):
    global record_seconds
    # Retirer la tâche des futures tâches
    task = next((t for t in tasks if t['id'] == task_id), None)
    if task:
        tasks.remove(task)
        task['time'] = time.time()  # Mettre à jour l'heure d'exécution
        task_history.append(task)   # Déplacer dans l'historique
        save_tasks()  # Sauvegarder après suppression

    #print(f"Task starts {task_id} executed: {description}")
    #time.sleep(10)
    #print(f"Task ends {task_id} executed: {description}")

    # Création de l'enregistreur
    recorder = PvRecorder(device_index=-1, frame_length=CHUNK)
    recorder.start()
   
    output_file = "%s.wav"%(datetime.now().strftime(fmt_output)) 

    print("[START in %s]"%(output_file))
    # Ouverture du fichier WAV en écriture
    wavefile = wave.open(output_file, 'wb')
    wavefile.setnchannels(CHANNELS)
    wavefile.setsampwidth(2)  # 2 octets pour 16 bits (int16)
    wavefile.setframerate(RATE)
  
    print(record_seconds)

    for _ in range(0, int(RATE / CHUNK * int(record_seconds))):
        data = recorder.read()  # Lire un bloc de données
        # Convertir la liste en binaire (en int16)
        binary_data = struct.pack('<' + ('h' * len(data)), *data)
        wavefile.writeframes(binary_data)  # Écrire immédiatement dans le fichier
   
    print("[End]")
    recorder.stop()
    recorder.delete()
    wavefile.close()


# Classe qui va gérer les interactions via une interface web
class TaskSchedulerWebApp:

    @cherrypy.expose
    def index(self):
        return """
            %s
            <h2>Interface</h2><br>
            <a href="/list_future_tasks">List Future Tasks</a><br><br>
            <a href="/list_past_tasks">List Past Tasks</a><br><br>
            <a href="/schedule_task_calender">Schedule New Task</a><br><br>
            <a href="/remove_task_form">Remove Task</a><br>
        """%(style)

    @cherrypy.expose
    def list_future_tasks(self):
        t = datetime.now().strftime(fmt)
        response = f"%s<h2>List Future Tasks</h2>[Current time]<br>[{t}]<br>"%(style)
        if len(tasks)>0:
            for task in tasks:
                t = datetime.fromtimestamp(task['time']).strftime(fmt)
                #response += f"<br>[{task['id']}][{t}][{task['description']}]"
                response += f"<br>[{task['id']}][{task['description']}]<br>[{t}]<br>"
        else:
            response += f"<h3>No future tasks</h3>"
        response += "<br><a href='/'>Back to Home</a>"
        return response

    @cherrypy.expose
    def list_past_tasks(self):
        t = datetime.now().strftime(fmt)
        response = f"%s<h2>List Past Tasks</h2>[Current time]<br>[{t}]<br>"%(style)
        if len(task_history)>0:
            for task in task_history:
                t = datetime.fromtimestamp(task['time']).strftime(fmt)
                response += f"<br>[{task['id']}][{task['description']}]<br>[{t}]<br>"
        else:
            response += f"<h3>No past tasks</h3>"
        response += "<br><a href='/'>Back to Home</a>"
        return response

    #@cherrypy.expose
    #def schedule_task_form(self):
    #    return """
    #    %s
    #    <h2>Schedule a New Task</h2>
    #    <form method="get" action="schedule_task">
    #      <label>Description: <input type="text" name="description" /></label><br>
    #      <label>Delay (seconds): <input type="number" name="delay" /></label><br>
    #      <input type="submit" value="Schedule Task" />
    #    </form>
    #    <a href='/'>Back to Home</a>
    #    """%(style)

    @cherrypy.expose
    def schedule_task_calender(self):
        now = datetime.now()
        value_date = now.strftime(fmt_calender) 
        min_date   = value_date
        next_year = now.year + 10
        max_date = now.replace(year=next_year).strftime(fmt_calender)
        return f"""
        %s
        <h2>Schedule a New Task</h2>
        <form method="get" action="schedule_task">
        <input type="datetime-local"
         name="schedule_task_time"
         value="{value_date}"
         min="{min_date}"
         max="{max_date}" />
        <label>Duration (seconds): <input type="number" name="duration" value=5400 /></label><br>
        <input type="submit" value="Schedule Task" />
        </form>
         <a href='/'>Back to Home</a>
        """%(style)

    #@cherrypy.expose
    #def schedule_task(self, description, delay):
    #    global task_id_counter
    #    delay = int(delay)
    #    task_time = time.time() + delay
    #    task_id = task_id_counter
    #    task_id_counter += 1
    #    
    #    # Ajouter la tâche dans le planificateur
    #    scheduler.enter(delay, 1, task_action, argument=(task_id, description))
    #    tasks.append({"id": task_id, "description": description, "time": task_time})
    #    
    #    save_tasks()  # Sauvegarder après ajout de la tâche

    #    return f"%sTask {task_id} scheduled for {delay} seconds from now.<br><a href='/'>Back to Home</a>"%(style)

    @cherrypy.expose
    def schedule_task(self, schedule_task_time, duration):
        global task_id_counter
        global record_seconds
        record_seconds = duration
        task_time = (datetime.strptime(schedule_task_time, fmt_calender)).timestamp()
        delay = task_time - time.time()
        schedule_task_time_fmt = datetime.fromtimestamp(task_time).strftime(fmt)
        task_id = task_id_counter
        task_id_counter += 1
       
        #print()
        #print(schedule_task_time)
        #print(task_time)
        #print(schedule_task_time_fmt)
        #print()
        description = "Task %d"%(task_id_counter)
        # Ajouter la tâche dans le planificateur
        scheduler.enter(delay, 1, task_action, argument=(task_id, description))
        tasks.append({"id": task_id, "description": description, "time": task_time})
        save_tasks()  # Sauvegarder après ajout de la tâche
        return f"%sTask {task_id} scheduled to {schedule_task_time_fmt} <br><a href='/'>Back to Home</a>"%(style)


    @cherrypy.expose
    def remove_task_form(self):
        form = """
        %s
        <h2>Remove a Task</h2>
        <form method="get" action="remove_task">
          <label>Task ID: <input type="number" name="task_id" /></label><br>
          <input type="submit" value="Remove Task" />
        </form>
        <a href='/'>Back to Home</a>
        """%(style)
        return form

    @cherrypy.expose
    def remove_task(self, task_id):
        task_id = int(task_id)
        # Trouver la tâche et la retirer
        for task in tasks:
            if task["id"] == task_id:
                # La retirer de la file du planificateur
                for event in scheduler.queue:
                    if event.argument[0] == task_id:
                        scheduler.cancel(event)
                        tasks.remove(task)
                        save_tasks()  # Sauvegarder après suppression
                        return f"%sTask {task_id} removed.<br><a href='/'>Back to Home</a>"%(style)
        
        return f"%sTask {task_id} not found.<br><a href='/'>Back to Home</a>"%(style)

# Charger les tâches au démarrage
load_tasks()

# Lancer le serveur web CherryPy
if __name__ == '__main__':
    cherrypy.quickstart(TaskSchedulerWebApp(), '/', {
        'global': {
            'server.socket_host': '192.168.1.52',
            'server.socket_port': 8080,
        }
    })

