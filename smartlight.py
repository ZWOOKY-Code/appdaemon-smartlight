import appdaemon.plugins.hass.hassapi as hass
import appdaemon.plugins.hass
from datetime import datetime , timedelta
import threading


"""
https://community.home-assistant.io/t/app-2-smart-light/129011/6  derived from

App to automatically turn lights on/off for a certain time depending on the input of one or multiple motions sensors.

Args:
    light_entities - the light(s)/switch(s) that shall be controlled - switch on or off
    motion_entities - a list of motion sensors

    lux_entity (optional) - the sensor that returns the current illuminance 
    lux_limit (optional) - the light will not be turned on if the lux_entity returns a value smaller than the lux_limit

    brightness_entity (optional) - entity for brightness setting - only when switching individual lights
    brightness (optional) - brighntess - only when switching individual lights

    light_timeout (optional) - the time in seconds after which the lights shall be turned off. Each motion event restarts the timer
    
    transition (optional) - the time in seconds to reach final brightness - doesn't work at the moment
    restart_timer (optional) - yes      - restart in any case!! 
                             - motion   - restart only if motion activated light!! - this is the default
                             - no       - no !!

    disable_motion_sensor_entities (optional) - switch entities that can enable/disable the automatic light on/off handling
    somebody_is_home_entity (optional) - only switch lights when somebody is home    

    Scene Stuff -------------------------------------------------------------------------
    scene_on_activate_clear_timer  -  if clear clears_timer of lights
    scene_entity  -  if starts scene instead switching lights
    scene_timeout -  if scene is activated or called this is the scene timeout only in combination with scene_on_activate_clear_timer
    scene_listen_entities  -  listens for this scenes if activated and restarts timer
    scene_restart (optional) - False    - default - timer will not be restarted if scene is allready running and we got motion 
                             - True   - restart scene if motion is detected
    monitor_light_timeout - prints a list of running timers in log
    monitor_light_entities - if one or more lights of this scenes are on - the scene will not called

Changes from stoellchen:
    20201225:  
    	lux_limit changed from int to float
    	motion_entity changed to motion_entities and checking lights to switch on or off
    	disable_motion_sensor_entity switched to list  room-disable and global disable

# Example:
# WZi:
#  module: smartlight
#  class: SmartLight
#  status_timers: 300
#  somebody_is_home_entity: group.family
#  light_entities: 
#     - light.wand
#     - light.sideboard_rechts
#     - light.sideboard_links
#  scene_on_activate_clear_timer: clear
#  scene_entity: scene.scene_sensor_wohnzimmer_1
#  scene_timeout: 7200
#  scene_restart: True
#  scene_listen_entities:
#    - scene.scene_sensor_wohnzimmer_1
#    - scene.scene_sensor_wohnzimmer_2
#    - scene.hell
#    - scene.tv_blau
#    - scene.tromso_mit_licht_unten_blau_rot_dunkel
#    - scene.tromso_mit_licht_unten
#    - scene.sideboard_bild_turkis
#    - scene.tracey_lights
#    - scene.scene_wohnzimmer_esszimmer_1
#    - scene.scene_wohnzimmer_esszimmer_2
#  monitor_light_timeout: 3600
#  monitor_light_entities: 
#    - light.wand
#    - light.sideboard_links
#    - light.sideboard_rechts
#    - light.wohnzimmer_links
#    - light.wohnzimmer_rechts
#    - light.wohnzimmer_licht_1
#    - light.wohnzimmer_licht_2
#    - light.wohnzimmer_licht_3
#    - light.wohnzimmer_licht_4
#    - switch.lichtvorhang
#    - switch.lichterkette
#    - switch.tromso
#  motion_entities: 
#    - binary_sensor.ms1
#    - binary_sensor.ms3
#  lux_entity: sensor.ms1
#  lux_limit: 35
#  brightness_entity: sensor.template_motion_sensor_light_brightness
#  transition: 10
#  light_timeout: 60
#  restart_timer: 'motion'
#  disable_motion_sensor_entities: 
#    - input_boolean.global_motion_no_switch_light
#    - input_boolean.disable_wohnzimmer_motion
#  disable_timer_entities: 
#    - input_boolean.disable_wohnzimmer_timer


"""

class SmartLight(hass.Hass):

    def initialize(self):
        self.__single_threading_lock = threading.Lock()

        try:
            self._status_timers = int(self.args.get('status_timers', 0))
            self._light_entities = self.args.get('light_entities', None)
            self._motion_entities = self.args.get('motion_entities', None)
            self._lux_entity = self.args.get('lux_entity', None)
            self._lux_limit = int(self.args.get('lux_limit', 0))
            self._brightness_entity = self.args.get('brightness_entity', None)
            self._brightness = int(self.args.get('brightness', 100))
            self._light_timeout = int(self.args.get('light_timeout', 0))
            self._transition = int(self.args.get('transition',0))
            self._restart_timer = self.args.get('restart_timer', 'motion')
            self._restart_timer_state = "-"
            self._disable_motion_sensor_entities = self.args.get('disable_motion_sensor_entities', None)
            self._disable_timer_entities = self.args.get('disable_timer_entities', None)
            self._somebody_is_home = self.args.get('somebody_is_home_entity', None)

            self._scene_on_activate_clear_timer = self.args.get('scene_on_activate_clear_timer', None)
            self._scene_entity = self.args.get('scene_entity', None)
            self._scene_timeout = int(self.args.get('scene_timeout', 18000))
            self._scene_listen_entities = self.args.get('scene_listen_entities', None)
            self._scene_restart = self.args.get('scene_restart', None)
            self._monitor_light_timeout = int(self.args.get('monitor_light_timeout', 180 ))
            self._monitor_light_entities = self.args.get('monitor_light_entities', None)
            
            

            self._last_scene_activated ='-'

        except (TypeError, ValueError):
            self.log("Invalid Configuration", level="ERROR")
            return

        self.log("---------------------------------------------------------------------------------", level="INFO")
        self.log("--", level="INFO")
        self.log("-- ", level="INFO")
        self.log("--", level="INFO")
        self.log("---------------------------------------------------------------------------------", level="INFO")
        
        if type(self._motion_entities) != list:
            self.log('motion_entities must be a list of entities', level="ERROR")
        
        if type(self._light_entities) != list:
            self.log('light entities must be a list of entities.', level="ERROR")
            return

        if self._lux_limit > 0 and self._lux_entity is None:
            self.log('lux_limit given but no lux_entity specified', level="ERROR")
            return
		
        if self._transition <= 0:
            self.log('_transiton <=0 0 will be used', level="INFO")
            self._transition = 0
        elif self._transition >= 120:
            self.log('transition >120 120 will be used', level="INFO")
            self._transition = 120
        else:
            self.log('transition {} will be used'.format( self._transition ), level="INFO")

        if self._brightness is None:
            self.log('brightness not given 100 will be used', level="INFO")
            self._brightness = 100
        else:
            if self._brightness <=0:
                self.log('brightness <=0 20 will be used', level="INFO")
                self._brightness = 20
            elif self._brightness >100:
                self.log('brightness >100 100 will be used', level="INFO")
                self._brightness = 100
            else:
                self.log('brightness {} will be used'.format( self._brightness ), level="INFO")
#                self._brightness = 100
        if self._brightness_entity is None:
            self.log("brighntes_sensor is None - brightness {} will be used".format( self._brightness ), level="INFO")
        else:
            self.log('brightness from {} will be used current {}' .format(self._brightness_entity,self.get_state( self._brightness_entity )) , level="INFO")

        if self._somebody_is_home is None:
            self.log("Somebody_is_home doesn't matter", level="WARNING")

        if self._light_timeout == 0:
            self.log('No timeout given. 5s will be used by default.', level="WARNING")
            self._light_timeout = 5

        if self._restart_timer == 'motion':
            self.log('restart timer when motion activated: motion')
        elif self._restart_timer == 'no':
            self.log('Do NOT restart timer even when motion is detected: no')
        elif self._restart_timer == 'yes':
            self.log('Restart timer even when motion is detected: yes')
        else:
            self._restart_timer = 'motion'
            self.log('Restart timer default: motion activated' ,level="WARNING")
            
        if self._scene_restart != None:
            if self._scene_restart == True:
                self.log('Restart scene timer when motion activated True',level="INFO")
            elif self._scene_restart == False:
                self.log('restart scene timer even when motion is detected',level="INFO")
            else:
                self.log('Restart scene timer default: False wrong param{}'.format( self._scene_restart ) ,level="WARNING")
                self._scene_restart = False
        else:
            self._scene_restart = False
            self.log('Restart scene timer default: False' ,level="WARNING")


        if type(self._disable_motion_sensor_entities) is list:
            self.log('disable motion switches is defined .', level="INFO")
        else:
            if type(self._disable_motion_sensor_entities) != list:
                self._disable_motion_sensor_entities = None
                self.log('disable motion switches must be a list of entities .', level="WARNING")

        if type(self._disable_timer_entities) is list:
            self.log('disable timers defined .', level="INFO")
        else:
            if type(self._disable_timer_entities) != list:
                self._disable_timer_entities = None
                self.log('disable timers must be a list of entities .', level="WARNING")


        if self._scene_on_activate_clear_timer is None:
           self._scene_on_activate_clear_timer ="off"
        elif self._scene_on_activate_clear_timer != "clear":
           self._scene_on_activate_clear_timer ="off"
        self.log('Scene - cancel timer:{}'. format(self._scene_on_activate_clear_timer) , level="INFO")            
                    
        if self._scene_entity != None:
            try:
                if self.get_state(self._scene_entity) == "scening":
                    self.log('Scene {} instead of lights.'.format(self._scene_entity), level="INFO")
            except (ValueError, TypeError):
                self.log('Scene {} does not exist.'.format(self._scene_entity), level="WARNING")
                self._scene_entity = None   
        
        if self._scene_timeout is None:
            self.log('scene timeout not given 18000 will be used', level="INFO")
            self._scene_timeout = 18000
        else:
            if self._scene_timeout <=0:
                self.log('Scene timeout <=20 20 will be used', level="INFO")
                self._scene_timeout = 20
            elif self._scene_timeout >43200:
                self.log('Scene timeout >43200 43200 will be used', level="INFO")
                self._scene_timeout = 43200
            else:
                self.log('Scene timeout {} will be used'.format( self._scene_timeout ), level="INFO")

        if self._monitor_light_timeout is None:
            self.log('Monitor light timeout not given 18000 will be used', level="INFO")
            self._monitor_light_timeout = 18000
        else:
            if self._monitor_light_timeout <=0:
                self.log('Monitor light timeout <=20 20 will be used', level="INFO")
                self._monitor_light_timeout = 20
            elif self._monitor_light_timeout >43200:
                self.log('Monitor light timeout >43200 43200 will be used', level="INFO")
                self._monitor_light_timeout = 43200
            else:
                self.log('Monitor light timeout {} will be used'.format( self._monitor_light_timeout ), level="INFO")

        if type(self._monitor_light_entities) is list:
            self.log('Monitor lights to listen {} will be used'.format( self._monitor_light_entities ), level="INFO")


        self._last_scene_activated='-'
        if type(self._scene_listen_entities) is list:
            self.log('Scene to listen {} will be used'.format( self._scene_listen_entities ), level="INFO")


        # this is used to turn off individual lights after a specific time
        # the lights are take from the scenes and each light get's his own timer based on yaml definitions
        # because we also want keep track of individual lights we need to listen on them - we need a default timeout for them
        # lights turn of while switching to another scene or turn off by a script need to be removed from the array of timers
        # each light should only be defined in one smartlight class!!!!!
        # one thing is, a light which was in a scene and now another one is activeted what should happen with them?
        # scenes need to define all lamps in the same room to switch them on and off, otherwise the will stay on too long after
        # the scene as changed without reinit of all lights!!!
        self._RunningTimers = {}
        if self._status_timers != 0:
        	self.log('status of timers will be shown all {}s'.format(self._status_timers) )
        tRT = self.run_in(self.status_timers_callback, self._status_timers   )
        self.SetTimerInfo(  tRT , 'status_timers', self._status_timers , 'Monitoring','monitor' )        


        # checking lights already switched on
        # for light_entity in self._light_entities:
        #    if self.get_state(light_entity) == "on":
        #         self.log('light ' + light_entity + " is already on.")
        #         self.restart_timer('startup')

        if type(self._scene_listen_entities) is list:
            tempStatus='-'
            for lscene_entity in self._scene_listen_entities:
                if self.get_state( lscene_entity ) == "scening":
                    tempStatus=lscene_entity
            if tempStatus!='-':
                # filter on entity does not work - we get all scenes - looking later for the correct scene
                self.listen_event(self.scene_detected_callback, event='call_service', domain='scene', service='turn_on', entity_id = tempStatus  ,new="also")
                             
        for motion_entity in self._motion_entities:
            self.listen_state(self.motion_detected_callback, motion_entity, new="on")
            
        # initialize listening on light status in addition to scenes
        # self.listen_state(self.my_callback, "light")
        if type(self._monitor_light_entities) is list:
            for light_entity in self._monitor_light_entities:
                self.listen_state(self.keep_track_of_individual_lights_state_changed_callback, light_entity , duration = 5 )
                if self.get_state(light_entity) == "on":
                    self.log('light ' + light_entity + " is already on.")
                    self.keep_track_of_individual_lights_state_changed_callback( light_entity, "none", "none", 'on','')

            
        if type(self._disable_motion_sensor_entities) is list:
            for disable_entity in self._disable_motion_sensor_entities:
                self.listen_state(self.motion_sensor_disabled_callback, disable_entity )

        if type(self._disable_timer_entities) is list:
            for disable_entity in self._disable_timer_entities:
                self.log('start listen_state for: {}'.format( disable_entity ) )
                self.listen_state(self.timer_disabled_callback, disable_entity )

        try:
            ambient_light = float(self.get_state(self._lux_entity) )
            self.log("INITIALIZED: Ambient: {} ({}) for {}".format(ambient_light, self._lux_limit , self._lux_entity ))
        except (ValueError, TypeError):
            self.log("INITIALIZED: Could not get Ambient Light Level for " + self._lux_entity , level="ERROR")


    def SetTimerInfo(self, timer_handle , timer_name, timer_time , timer_reason,timer_scene_or_light ): 
  	    # self.log('handle:{} ' , format( timer_handle) )
  	    # self.log('name:{} ' ,  format( timer_name) )
  	    # self.log('time:{} ' ,  format( timer_time) )
  	    # self.log('reason:{} ' ,  format( timer_reason) )
  	    self._RunningTimers[timer_name] = { 'name' : timer_name 
  	                                    , 'handle' : timer_handle 
  	                                     ,'started': datetime.now( )
  	                                      ,'stop' : datetime.now( ) + timedelta( seconds=timer_time )
  	                                      , 'time' : timer_time
  	                                    , 'reason' : timer_reason 
  	                                    , 'los' : timer_scene_or_light 
  	                                    }

    def is_timer_disabled(self):
        if self._disable_timer_entities != None:
            for disable_entity in self._disable_timer_entities:
                return self.get_state( disable_entity ) == "on"
        return False 

    def timer_disabled_callback(self, entity, attribute, old, new, kwargs):
        self.log("Smartlights timer disabled: {}".format(self.is_timer_disabled()))
        if self.is_timer_disabled() == True:
            # self.stop_timer('Smartlight timer now disabled - killed all running timers')
            self.kill_all_timers('timer '+entity+' disabled')
        else:
            # self.stop_timer('Smartlight timer now enabled - restarted all running timers')
            self.restart_all_timers('timer '+entity+' enabled')
        
    def is_motion_sensor_disabled(self):
        if type(self._disable_motion_sensor_entities) is list:
            for disable_entity in self._disable_motion_sensor_entities:
                if self.get_state( disable_entity ) ==  True:
                    return True
        return False 

    def motion_sensor_disabled_callback(self, entity, attribute, old, new, kwargs):
        # self.log("Smartlights motion sensor disabled: {}".format(self.is_motion_sensor_disabled()))
        if self.is_motion_sensor_disabled() == True:
            # self.stop_timer('Smartlight motion sensor now disabled - killed all running timers')
            self.kill_all_timers( 'motion sensor '+entity+' disabled'   )
        else:
            # self.restart_timer('Smartlight motion sensor now enabled - restarted all timers')
            self.restart_all_timers( 'motion sensor '+entity+' enabled'   )

    def get_my_brightness(self):
        if self._brightness_entity is None:
            return self._brightness
        else:
            return self.get_state( self._brightness_entity )

    # def scene_detected_callback(self,entity_id,attribute,old,aa):
    def scene_detected_callback(self,entity,attribute,kwargs):
        self.scene_detected(self,attribute,kwargs)
        
    def motion_detected_callback(self, entity, attribute, old, new, kwargs):
        self.motion_detected()

    def scene_detected(self ,entity,attribute,kwargs):
        with self.__single_threading_lock: # prevents code from parallel execution e.g. due to multiple consecutive events
            # self.log("scene detected  {}" . format( attribute['service_data']['entity_id'] ))
            if attribute['service_data']['entity_id'] in self._scene_listen_entities:
                self.log("OUR scene detected {}" . format( attribute['service_data']['entity_id'] ))
                # change last_scene_activated to current running if it's one we need to know
                self._last_scene_activated=attribute['service_data']['entity_id']
                # self.stop_timer('motion scene')
                # self.log("timers stopped because of scene:{}" . format( attribute['service_data']['entity_id'] ))
                # self.start_timer('motion scene')
                # we need to reinitialize our timers!!!
                self.keep_track_of_scene(self,'Current Scene','on',self._scene_timeout)
                if self._scene_restart == True:
                    self._restart_timer_state ="motion scene"
                    # restart lights because we got motion for scene
                    entities_of_scene = self.get_state( self._last_scene_activated ,attribute = "all" )
                    scene_entities = entities_of_scene['attributes']['entity_id']
                    lightsOnInScene =0
                    for check_light_entity in self._monitor_light_entities:
                        # self.log('CHECK 1 for {}' . format(check_light_entity) , level="INFO")
                        if self.get_state( check_light_entity ) =='off':
                            self.keep_track_of_individual_lights(self, check_light_entity,self._scene_timeout,'off','')
                        else:
                            # self.log('CHECK 2 for {} in' . format(check_light_entity) , level="INFO")
                            if check_light_entity in scene_entities:
                                # self.log('CHECK 3 for {} in' . format(check_light_entity) , level="INFO")
                                self.keep_track_of_individual_lights(self, check_light_entity,self._scene_timeout,'on','')
                                lightsOnInScene = lightsOnInScene +1
                            else:
                                self.keep_track_of_individual_lights(self, check_light_entity,self._monitor_light_timeout,'on','')                    
                    self.log('scene restart for {}' . format(self._last_scene_activated) , level="INFO")
                else:
                    self.log('no scene restart for {}'.format(self._last_scene_activated) , level="INFO")
                self.keep_track_of_scene(self,'Current Scene','on',self._scene_timeout)
                self.status_timers_info(self) # bring current lights status
            else:
                dummy=1
                # self.log("Do nothing we are not listening on this scene ({})".format(attribute['service_data']['entity_id']) ,level="INFO")

    def motion_detected(self):
        with self.__single_threading_lock: # prevents code from parallel execution e.g. due to multiple consecutive events
            self.log("Motion detected " )
            if self.is_motion_sensor_disabled() == True:
                self.log("... but motion sensor disabled")
                return

            if self._somebody_is_home != None:
                if self.get_state(self._somebody_is_home) != "home":
                    self.log("... but nobody is at home {}" .format( self.get_state(self._somebody_is_home) ) )
                    return
            
            if self._lux_limit > 0:
                try:
                    ambient_light = float(self.get_state(self._lux_entity) )
                    if ambient_light >= self._lux_limit:
                        self.log("Ambient light:{} (lmt:{}) - do nothing - stop".format(ambient_light, self._lux_limit))
                        return
                    else:
                        self.log("Ambient light:{} (lmt:{}) - go on".format(ambient_light, self._lux_limit))        
                except (ValueError, TypeError):
                    self.log("Could not get Ambient Light Level for " + self._lux_entity , level="WARNING")
                    return

            # self.log( '########  \nrestart_state:{} \nscene_restart:{} \nlast_sceneActi:{} ' . format( self._restart_timer_state , self._scene_restart , self._last_scene_activated ) )
            # first we need to check if a scene is running and we have an eye on this
            # if we have a scene it must be in our focus, because we check this before
            if self._last_scene_activated != '-':
                # restart scene was configured - now checking if a scene is already running
                lightsOnInScene = 0
                if self._scene_restart == True:
                    self._restart_timer_state ="motion scene"
                    # restart lights because we got motion for scene
                    entities_of_scene = self.get_state( self._last_scene_activated ,attribute = "all" )
                    scene_entities = entities_of_scene['attributes']['entity_id']
                    for check_light_entity in self._monitor_light_entities:
                        # self.log('CHECK 1 for {}' . format(check_light_entity) , level="INFO")
                        if self.get_state( check_light_entity ) =='off':
                            self.keep_track_of_individual_lights(self, check_light_entity,self._scene_timeout,'off','')
                        else:
                            # self.log('CHECK 2 for {} in' . format(check_light_entity) , level="INFO")
                            if check_light_entity in scene_entities:
                                # self.log('CHECK 3 for {} in' . format(check_light_entity) , level="INFO")
                                self.keep_track_of_individual_lights(self, check_light_entity,self._scene_timeout,'on','')
                                lightsOnInScene = lightsOnInScene +1
                            else:
                                self.keep_track_of_individual_lights(self, check_light_entity,self._monitor_light_timeout,'on','')                    
                    self.log('scene restart for {} finished' . format(self._last_scene_activated) , level="INFO")
                else:
                    self.log('no scene restart for {}'.format(self._last_scene_activated) , level="INFO")
                self.keep_track_of_scene(self,'Current Scene','on',self._scene_timeout)
                self.status_timers_info(self) # bring current lights status
                if lightsOnInScene > 0:
                    return   # stop further processing !!!!!!!!!!!!!!! 

            # now if no scene is running, check if we have a scene to start !!!!
            if self._scene_entity != None:
                if self.get_state(self._scene_entity) == "scening":    # make sure again, that it's a scene
                    self._last_scene_activated = self._scene_entity    # store for later processing
                    self.turn_on( self._scene_entity )
                    self.log("Scene {} turned on.".format( self._scene_entity ), level="INFO")
                    # timers will be set in lights on :-)
                    self.keep_track_of_scene(self,'Current Scene','on',self._scene_timeout)
                    self.status_timers_info(self) # bring current lights status
                    return   # stop further processing !!!!!!!!!!!!!!! 

            # we don't have a scene running or had to start one - starting lights !!!!
            else:
                self.keep_track_of_scene(self,'Current Scene','off',self._scene_timeout)
                for light_entity in self._light_entities:
                    light_state = self.get_state( light_entity )
                    if light_state not in ['off', 'on']:
                        self.log("Invalid light state for {}: {}. Expecting either on or off.".format(light_entity,light_state), level="ERROR")
                        # we don't return, because we want to keep it running
                    elif light_state == 'off':
                        self.log('turn light on {}'.format(light_entity) )
                        self.turn_on_light(light_entity) ## everything else is handled later
                    else:
                        self.log('light is already on {}'.format(light_entity) )
                        if self._restart_timer =='yes':
                            self.keep_track_of_individual_lights(self, light_entity,self._monitor_light_timeout,'on','')
                self.status_timers_info(self) # bring current lights status

    def status_timers_callback(self,kwargs):
        try:
            # just in case we called this by hand and not by timer
            self.cancel_timer( self._RunningTimers['status_timers']['handle'] )
            del self._RunningTimers['status_timers']
        except (ValueError, TypeError):
            self.log('ERROR killing timer status_timers',level="ERROR")
            dummy =1	
        self.status_timers_info(self)
        tRT = self.run_in(self.status_timers_callback, self._status_timers   )
        self.SetTimerInfo(tRT, 'status_timers', self._status_timers , 'Monitoring','monitor' ) 
        
    def status_timers_info(self,kwargs):
        for check_entity_in_timers in self._RunningTimers:
            # self.log( 'startet:'+ self._RunningTimers[ check_entity_in_timers ]['started'].strftime("%H:%M:%S")
            if self._RunningTimers[ check_entity_in_timers ]['los']  !='monitor':
                self.log( 'started:'+ self._RunningTimers[ check_entity_in_timers ]['started'].strftime("%H:%M:%S")
                          + ' stop:' + self._RunningTimers[ check_entity_in_timers ]['stop'].strftime("%H:%M:%S")
                          + ' ' + str( int( ((self._RunningTimers[ check_entity_in_timers ]['stop']-datetime.now() ).total_seconds() ) / 60) )
                          + '/' + str( int( self._RunningTimers[ check_entity_in_timers ]['time']/60)) +'m'
                         +' '+ self._RunningTimers[ check_entity_in_timers ]['reason']
                         +' '+ check_entity_in_timers 
                         +' '+ self._RunningTimers[ check_entity_in_timers ]['los'] 
                         )
        


    def keep_track_of_individual_lights_state_changed_callback(self, light_entity, attribute, old, new, kwargs):
        # state changed of switch or light - we work with a five second timeout in filter!!!
        # first check if the light is in active scene if yes use the scene timeout for this light
        # otherwise use light timeout for it
        # self.log('got state change {} {} {} {} {}'.format(light_entity, attribute, old, new, kwargs) )
        new_timeout = 30
        # self.log('got state change ------------- 1 {}'.format(self._last_scene_activated)  )
        if self._last_scene_activated !='-':
            entities_of_scene = self.get_state( self._last_scene_activated ,attribute = "all" )
            if type(entities_of_scene['attributes']['entity_id']) is list: 
                # self.log('got state change ------------- 2 {}'.format(entities_of_scene)  )
                if light_entity in entities_of_scene['attributes']['entity_id']:
                    # self.log('got state change ------------- 3'  )
                    new_timeout = self._scene_timeout
                elif light_entity in self._monitor_light_entities:
                    new_timeout = self._monitor_light_timeout
            else:
                self.log('this scene {} has no entities light:{}'.format(self._last_scene_activated,light_entity) )        
        else:
            if light_entity in self._monitor_light_entities:
                new_timeout = self._monitor_light_timeout
        self.keep_track_of_individual_lights(self, light_entity,new_timeout,new,kwargs)
            
    
    def keep_track_of_scene_callback( self,dummy,light_entity,light_timeout, light_action ,kwargs ):
        self.log('keep_track_of_scene_callback called')
        
    def keep_track_of_scene(self,scene,status,time,kwargs):
        if status =='off':
            if scene in self._RunningTimers:
                self.cancel_timer( self._RunningTimers[scene]['handle'] )
                del self._RunningTimers[ scene ]
        if status =='on' or status =='restart':
            tRT = self.run_in(self.keep_track_of_scene_callback, time , scene   )
            self.SetTimerInfo(tRT, scene , time  , status , 'scene' ) 
        
            
    def keep_track_of_individual_lights( self,dummy,light_entity,light_timeout, light_action ,kwargs ):
        #  action:  off
        #           on
        #           restart, but that's the same as on
        # self.log('got state change le:{} t:{} a:{} k:{}'.format(light_entity,light_timeout, light_action ,kwargs) )
        if light_action == 'on' or light_action == 'restart' or light_action == 'off':
            try:
                temp ='none'
                if light_entity in self._RunningTimers:
                    # try to cancel timer if we allready have it running 
                    temp = self._RunningTimers[ light_entity ]
                    self.cancel_timer( self._RunningTimers[ light_entity ]['handle'] )
                    del self._RunningTimers[ light_entity ]
                    # self.log('cancel timer for {}'.format( light_entity ) , level="INFO")
            except (ValueError, TypeError):
                self.log('cancel timer shot an error for {}'.format( light_entity ) , level="ERROR")
            if light_action == 'on' or light_action == 'restart':
                if self.is_timer_disabled() != 'on':
                    tRT = self.run_in(self.turn_off_individual_light, light_timeout , light_entity=light_entity )
                    self.SetTimerInfo(tRT, light_entity , light_timeout  , light_action , 'light' )
                # self.log('Timer created with {}s for {} '.format(light_timeout , light_entity) , level="INFO")
                if light_action == 'on':
                    self.log('{} is ON - t:{}'.format(light_entity,light_timeout) )
            else:
                self.log('{} is OFF'.format(light_entity) )
        else:
            self.log('unknown action for {}'.format(light_entity) , level="ERROR")

    def turn_off_individual_light( self,param  ):        
        # self.log('######### {}'.format(param  ) , level="INFO")
        try:
            del self._RunningTimers[ param['light_entity'] ]
            if param['light_entity'].split(".")[0] =="light":
                self.turn_off(param['light_entity'],transition = 1 )
            else:
                self.turn_off(param['light_entity'] )
            self.log('Timer expired for {}'.format(param['light_entity']) , level="INFO")
        except (ValueError, TypeError):
            self.log('Timer expired for {} shot an error'.format(param['light_entity']) , level="ERROR")

    def kill_all_timers( self , reason):
        self.log("KILL all running timers - {} ". format(reason) )
        tempTimers = {}
        tempCounter = 1
        for check_entity_in_timers in self._RunningTimers:
            # self.log('--- {} ---' . format( check_entity_in_timers ) )
            if self._RunningTimers[check_entity_in_timers]['los'] == 'light' or self._RunningTimers[check_entity_in_timers]['los'] == 'scene':
                tempTimers[ tempCounter ] = {'name': check_entity_in_timers
                                         , 'handle': self._RunningTimers[check_entity_in_timers]['handle']
                                        } 
                tempCounter = tempCounter + 1
        for tempDel in tempTimers:
            self.log("- Kill timer for {}" . format( tempTimers[tempDel]['name'] ) )
            self.cancel_timer( tempTimers[tempDel]['handle'] )
            del self._RunningTimers[ tempTimers[tempDel]['name'] ] 
        self.status_timers_info(self) # bring current lights status


    def restart_all_timers( self ,reason):
        self.log("RESTART all timers - {} ". format(reason) )
        for light_entity in self._monitor_light_entities:
            if self.get_state(light_entity) == "on":
                self.log('- restart ' + light_entity + " is already on. (restart)")
                self.keep_track_of_individual_lights_state_changed_callback( light_entity, "none", "none", 'on','')


    def turn_on_light(self,light_entity):
        light_entity_domain = light_entity.split(".")
        if light_entity_domain[0] == "light":
            self.turn_on( light_entity , brightness_pct = self.get_my_brightness(),color_name='white'  )
            self.log('Turning {} on - {} - brightness:{}% transition:{}' . format(light_entity_domain[0],light_entity,self.get_my_brightness() ,self._transition ))
        else:
            self.turn_on(light_entity)
            self.log('Turning {} on - {}' . format(light_entity_domain[0],light_entity))
    

    def turn_off_light(self, event_name = None, data = None, kwargs = None):
        self.log('Timer expired')
        self._timer = None
        self._timer_restart_state = "-"
        for light_entity in self._light_entities:
            self.log('Turning light off -' + light_entity)
            if light_entity.split(".")[0] =="light":
                self.turn_off(light_entity,transition = self._transition)
            else:
                self.turn_off(light_entity )
        if self._last_scene_activated !='-' and self._restart_timer_state=='motion scene':
            try:
                entities_of_scene = self.get_state( self._last_scene_activated ,attribute = "all" )
                self.log('shutting down all entities from scene {} timed out!!'.format(self._last_scene_activated))
                for entity_id in entities_of_scene['attributes']['entity_id']:
                    if entity_id.split(".")[0] =="light":
                        self.log('turn off LIGHT: {}'.format(entity_id))
                        self.turn_off( entity_id )
                    elif entity_id.split(".")[0] =="switch":
                        self.log('turn off SWITCH: {}'.format(entity_id))
                        self.turn_off( entity_id )
                    else:
                        self.log('turn off not defined: {}'.format(entity_id) , level="ERROR")
                self._last_scene_activated='-'
            except (ValueError, TypeError):
                self.log('ERROR in scene shutdown !!' ,level="WARNING")
            
        
