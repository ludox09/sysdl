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


#RECORD_SECONDS = 10
#RECORD_SECONDS = 5400
cherrypy.config.update({'log.screen': False,
                        'log.access_file': 'access.log',
                        'log.error_file': 'error.log'})

# Le planificateur et les données des tâches
scheduler = sched.scheduler(time.time, time.sleep)
tasks = []
tasks_history = []
task_id_counter = 0
fmt = "%a-%d/%m/%Y-%H:%M:%S"
fmt_output = "%a-%d%m%Y-%H%M%S"
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
           .wrapper-class input[type="radio"] {
               width: 15px;
           }
           .wrapper-class label {
               display: inline;
               margin-left: 5px;
           }
           current {
               color: #ffffaa;
           }
           </style>"""

OUTPUT_DIR="tasks_output"
TASK_FILE = "tasks.json"
FORMAT = 'int16'        # Format des données (16 bits)
CHANNELS = 1            # Nombre de canaux (mono)
RATE = 16000            # Taux d'échantillonnage (16 kHz)
CHUNK = 1024            # Taille des blocs de données


def prepare_output():
    if not os.path.exists(OUTPUT_DIR):
        os.mkdir(OUTPUT_DIR)

# Sauvegarder les tâches futures dans un fichier JSON
def save_tasks():
    with open(TASK_FILE, "w") as f:
        json.dump(tasks+tasks_history, f)

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
                elif abs(task_time_remaining) < task['duration']:
                    # Restaurer la tâche dans le scheduler
                    scheduler.enter(0, 1, task_action, argument=(task['id'], task['description']))
                    tasks.append(task)
                    task_id_counter = max(task_id_counter, task['id'] + 1)
                else:
                    # Restaurer la tâche dans la liste des tache passé
                    tasks_history.append(task)
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
    # Retirer la tâche des futures tâches
    task = next((t for t in tasks if t['id'] == task_id), None)
    if task:
        tasks.remove(task)
        task['time'] = time.time()  # Mettre à jour l'heure d'exécution
        duration = task['duration'] # Mettre à jour la durée
        tasks_history.append(task)   # Déplacer dans l'historique
        save_tasks()  # Sauvegarder après suppression

    #print(f"Task starts {task_id} executed: {description}")
    #time.sleep(10)
    #print(f"Task ends {task_id} executed: {description}")

    # Création de l'enregistreur
    recorder = PvRecorder(device_index=-1, frame_length=CHUNK)
    recorder.start()
   
    output_file = "%s/%s.wav"%(OUTPUT_DIR, datetime.now().strftime(fmt_output)) 

    #print("[START in %s]"%(output_file))
    # Ouverture du fichier WAV en écriture
    wavefile = wave.open(output_file, 'wb')
    wavefile.setnchannels(CHANNELS)
    wavefile.setsampwidth(2)  # 2 octets pour 16 bits (int16)
    wavefile.setframerate(RATE)
  
    #print(duration)

    for _ in range(0, int(RATE / CHUNK*duration)):
        data = recorder.read()  # Lire un bloc de données
        # Convertir la liste en binaire (en int16)
        binary_data = struct.pack('<' + ('h' * len(data)), *data)
        wavefile.writeframes(binary_data)  # Écrire immédiatement dans le fichier
   
    #print("[End]")
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
            <a href="/list_future_tasks">List Future Tasks</a><br>
            <a href="/list_past_tasks">List Past Tasks</a><br>
            <a href="/schedule_task_calender">Schedule New Task</a><br>
            <a href="/files/">Tasks output</a><br>
        """%(style)

    @cherrypy.expose
    def list_future_tasks(self):
        t = datetime.now().strftime(fmt)
        response = f"""%s<h2>List Future Tasks</h2>"""%(style)
        response += """<a href="/list_future_tasks">Refresh</a> <a href='/'>Back to Home</a> <br>"""
        response += f"""<current>[{t}][Current time]</current>"""
        if len(tasks)>0:
            for task in tasks:
                t = datetime.fromtimestamp(task['time']).strftime(fmt)
                response += f"""<br>[{t}][{task['id']}][{task['description']}]"""
        else:
            response += f"<h3>No future tasks</h3>"
        #response += "<br><a href='/'>Back to Home</a>"
        response += self.remove_task_form()
        return response

    @cherrypy.expose
    def list_past_tasks(self):
        t = datetime.now().strftime(fmt)
        response = f"""%s<h2>List Past Tasks</h2>"""%(style)
        response += """<a href="/list_past_tasks">Refresh</a> <a href='/'>Back to Home</a> <br>"""
        response += f"""<current>[{t}][Current time]</current>"""


        if len(tasks_history)>0:
            for task in tasks_history:
                t = datetime.fromtimestamp(task['time']).strftime(fmt)
                response += f"""<br>[{t}][{task['id']}][{task['description']}]"""
        else:
            response += f"<h3>No past tasks</h3>"
        #response += "<br><a href='/'>Back to Home</a>"
        response += self.remove_task_form()
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
         max="{max_date}" /><br>
         <select name="duration">
         <option value=5>5</option>
         <option value=10>10</option>
         <option value=15>15</option>
         <option value=60>60</option>
         <option value=100>100</option>
         <option value=3600>3600</option>
         <option value=5400 selected>5400</option>
         </select>
         <input type="submit" value="Schedule Task" />
         </form>
         <a href='/'>Back to Home</a>
        """%(style)

    @cherrypy.expose
    def schedule_task(self, schedule_task_time, duration):
        global task_id_counter
        duration =  int(duration)
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
        description = "Task %d %d"%(task_id_counter, duration)
        # Ajouter la tâche dans le planificateur
        scheduler.enter(delay, 1, task_action, argument=(task_id, description))
        tasks.append({"id": task_id, "description": description, "time": task_time, "duration": duration})
        save_tasks()  # Sauvegarder après ajout de la tâche
        response = f"%sTask {task_id} scheduled to {schedule_task_time_fmt} <br><a href='/'>Back to Home</a>"%(style)
        response += self.list_future_tasks
        return response


    @cherrypy.expose
    def remove_task_form(self):
        form = """
        <p>Remove a Task</p>
        <form method="get" action="remove_task">
          <label>Task ID: <input type="number" name="task_id" /></label><br>
          <input type="submit" value="Remove Task" />
        </form>
        <a href='/'>Back to Home</a>
        """
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

    @cherrypy.expose
    def files(self, path=""):
        # Chemin du répertoire de base
        base_dir = OUTPUT_DIR  # Remplace avec le chemin réel
        
        # Construire le chemin complet en ajoutant la partie 'path' si elle est présente
        full_path = os.path.join(base_dir, path)
        
        # Si c'est un fichier, le servir avec l'option de téléchargement
        if os.path.isfile(full_path):
            return cherrypy.lib.static.serve_file(full_path, "application/x-download", "attachment")
        
        # Si c'est un répertoire, lister son contenu
        elif os.path.isdir(full_path):
            # Liste les fichiers et dossiers
            files = os.listdir(full_path)
            
            # Créer une liste cliquable pour chaque fichier/dossier
            html = style
            html += f"<h2>Tasks output</h2><ul>"
            for file in files:
                file_path = os.path.join(path, file)
                html += f'<li><a href="/files/?path={file_path}">{file}</a></li>'
            html += "</ul>"
            html += "<br><a href='/'>Back to Home</a>"
            return html
        else:
            return "Path not found"


# Charger les tâches au démarrage
load_tasks()
prepare_output()

# Lancer le serveur web CherryPy
if __name__ == '__main__':
    cherrypy.quickstart(TaskSchedulerWebApp(), '/', {
        'global': {
            #'server.socket_host': '192.168.1.52',
            'server.socket_host': '0.0.0.0',
            'server.socket_port': 8080,
        }
    })

