import appdaemon.plugins.hass.hassapi as hass
import appdaemon.plugins.hass
import threading

"""
https://community.home-assistant.io/t/app-2-smart-light/129011/6

App to automatically turn lights on/off for a certain time depending on the input of one or multiple motions sensors.

Args:
    light_entity - the light/switch that shall be controlled
    motion_entities - a list of motion sensors
    lux_entity (optional) - the sensor that returns the current illuminance 
    lux_limit (optional) - the light will not be turned on if the lux_entity returns a value smaller than the lux_limit
    light_timeout (optional) - the time in seconds after which the lights shall be turned off. Each motion event restarts the timer
    transition (optional) - the time in seconds to reach final brightness
    restart_timer (optional) - yes      - restart in any case!! 
                             - motion   - restart only if motion activated light!! - this is the default
                             - no       - no !!
    brightness_entity (optional) - entity for brightness setting
    brightness (optional) - brighntess
    countdown_entity (optional) - a timer entity that can be used for the timeout handling. If this entity is set, the light_timeout argument will be ignored, because the entity already has its own timeout
    disable_motion_sensor_entities (optional) - switch entities that can enable/disable the automatic light on/off handling
    somebody_is_home_entity (optional) - only switch lights when somebody is home    

    Scene Stuff -
    scene_on_activate_clear_timer  -  if on clears_timer of lights
    scene_timeout -  if scene is activated or called this is the scene timeout only in combination with scene_on_activate_clear_timer
    scene_entity  -  if on clears_timer of lights
    scene_listen_entities  -  listens for this scenes if activated
    scene_restart (optional) - False    - default - timer will not be restarted if scene is allready running and we got motion 
                             - True   - restart scene if motion is detected

Changes from stoellchen:
    20201225:  
    	lux_limit changed from int to float
    	motion_entity changed to motion_entities and checking lights to switch on or off
    	disable_motion_sensor_entity switched to list  room-disable and global disable

# Example:
#  WohnzimmerMotionLight:
#    module: smartlight
#    class: SmartLight
#    light_entities: 
#       - light.wand
#       - light.sideboard_rechts
#       - light.sideboard_links
#    somebody_is_home_entity: group.family
#    motion_entities: 
#      - binary_sensor.ms1
#    lux_entity: sensor.ms1
#    lux_limit: 30
#    brightness_entity: sensor.template_motion_sensor_light_brightness
#    light_timeout: 300
#    disable_motion_sensor_entities: 
#      - input_boolean.disable_wohnzimmer_motion

"""

class SmartLight(hass.Hass):

    def initialize(self):
        self.__single_threading_lock = threading.Lock()

        try:
            self._light_entities = self.args.get('light_entities', None)
            self._motion_entities = self.args.get('motion_entities', None)
            self._lux_entity = self.args.get('lux_entity', None)
            self._lux_limit = int(self.args.get('lux_limit', 0))
            self._brightness_entity = self.args.get('brightness_entity', None)
            self._brightness = int(self.args.get('brightness', 100))
            self._light_timeout = int(self.args.get('light_timeout', 0))
            self._transition = int(self.args.get('transition',0))
            self._countdown_entity = self.args.get('countdown_entity', None)
            self._restart_timer = self.args.get('restart_timer', 'motion')
            self._restart_timer_state = "-"
            self._disable_motion_sensor_entities = self.args.get('disable_motion_sensor_entities', None)
            self._somebody_is_home = self.args.get('somebody_is_home_entity', None)

            self._scene_on_activate_clear_timer = self.args.get('scene_on_activate_clear_timer', None)
            self._scene_entity = self.args.get('scene_entity', None)
            self._scene_timeout = int(self.args.get('scene_timeout', 18000))
            self._scene_listen_entities = self.args.get('scene_listen_entities', None)
            self._scene_restart = self.args.get('scene_restart', None)
            self._last_scene_activated ='-'

        except (TypeError, ValueError):
            self.log("Invalid Configuration", level="ERROR")
            return

        if type(self._motion_entities) is not list:
            self.log('motion_entities must be a list of entities', level="ERROR")
        
        if type(self._light_entities) is not list:
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


        if self._countdown_entity is not None and self._light_timeout > 0:
            self.log('light_timeout will be ignored, because a countdown_entity is given. The timeout of the entity '+self._countdown_entity+ " will be used instead.", level="WARNING")

        if self._somebody_is_home is None:
            self.log("Somebody_is_home doesn't matter", level="WARNING")

        if self._countdown_entity is None and self._light_timeout == 0:
            self.log('No timeout given. 5s will be used by default.', level="WARNING")
            self._light_timeout = 5

        if self._restart_timer == 'motion':
            self.log('restart timer when motion activated')
        elif self._restart_timer == 'no':
            self.log('Do NOT restart timer even when motion is detected')
        elif self._restart_timer == 'yes':
            self.log('Restart timer even when motion is detected')
        else:
            self._restart_timer = 'motion'
            self.log('Restart timer default: motion activeded' ,level="WARNING")

        if self._scene_restart is not None:
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


        if self._disable_motion_sensor_entities is None:
            self.log('disable motion sensor(s) not defined .', level="WARNING")
        else:
            if type(self._disable_motion_sensor_entities) is not list:
                self._disable_motion_sensor_entities = None
                self.log('disable motion sensor(s) must be a list of entities .', level="WARNING")

        if self._scene_on_activate_clear_timer is None:
           self._scene_on_activate_clear_timer ="off"
        elif self._scene_on_activate_clear_timer != "clear":
           self._scene_on_activate_clear_timer ="off"
        self.log('Scene - cancel timer:{}'. format(self._scene_on_activate_clear_timer) , level="INFO")            
                    
        if self._scene_entity is not None:
            try:
                if self.get_state(self._scene_entity) == "scening":
                    self.log('Scene {} instead of lights.'.format(self._scene_entity), level="INFO")
            except (ValueError, TypeError):
                self.log('Scene {} does not exist.'.format(self._scene_entity), level="WARNING")
                self._scene_entity = None   
        
        if self._scene_timeout is None:
            self.log('scene timout not given 18000 will be used', level="INFO")
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
        self._last_scene_activated='-'
        if type(self._scene_listen_entities) is list:
            self.log('Scene to listen {} will be used'.format( self._scene_listen_entities ), level="INFO")

        self._timer = None
        if self._countdown_entity is not None:
            self.listen_event(self.turn_off_light, "timer.finished", entity_id = self._countdown_entity)
        
        for light_entity in self._light_entities:
            if self.get_state(light_entity) == "on":
                self.log('light ' + light_entity + " is already on.")
                self.restart_timer('startup')

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
            
        if self._disable_motion_sensor_entities is not None:
            for disable_entity in self._disable_motion_sensor_entities:
                self.listen_state(self.motion_sensor_disabled_callback, disable_entity )

        try:
            ambient_light = float(self.get_state(self._lux_entity) )
            self.log("INITIALIZED: Ambient: {} ({}) for {}".format(ambient_light, self._lux_limit , self._lux_entity ))
        except (ValueError, TypeError):
            self.log("INITIALIZED: Could not get Ambient Light Level for " + self._lux_entity)

    def is_motion_sensor_disabled(self):
        if self._disable_motion_sensor_entities is not None:
            for disable_entity in self._disable_motion_sensor_entities:
                return self.get_state( disable_entity ) == "on"
        return False 

    def motion_sensor_disabled_callback(self, entity, attribute, old, new, kwargs):
        self.log("Smartlights disabled: {}".format(self.is_motion_sensor_disabled()))
        if self.is_motion_sensor_disabled():
            self.stop_timer('Smartlight now disabled')
        else:
            self.restart_timer('Smartlight now enabled')

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
            self.log("scene detected  {}" . format( attribute['service_data']['entity_id'] ))
            if attribute['service_data']['entity_id'] in self._scene_listen_entities:
                self.stop_timer('motion scene')
                self.log("timers stopped because of scene:{}" . format( attribute['service_data']['entity_id'] ))
                self._last_scene_activated=attribute['service_data']['entity_id']
                self.start_timer('motion scene')
            else:
                self.log("Do nothing we are not listening on this scene")
                self._last_scene_activated='-'
                
    def motion_detected(self):
        with self.__single_threading_lock: # prevents code from parallel execution e.g. due to multiple consecutive events
            self.log("Motion detected " )
            if self.is_motion_sensor_disabled():
                self.log("... but motion sensor disabled")
                return

            if self._somebody_is_home is not None:
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


            self.log( '########  \nrestart_state:{} \nscene_restart:{} \nlast_sceneActi:{} ' . format( self._restart_timer_state , self._scene_restart , self._last_scene_activated ) )
            # first we need to check if a scene is running and we have an eye on this
            # if we have a scene it must be in our focus, because we check this before
            if self._last_scene_activated != '-':
                # restart scene was configured - now checking if a scene is already running
                if self._scene_restart == True:
                    self._restart_timer_state ="motion scene"
                    self.restart_timer( self._restart_timer_state )                       
                self.log("Scene {} restart timer ({}).".format( self._last_scene_activated , self._scene_restart ), level="INFO")
                return   # stop further processing !!!!!!!!!!!!!!! 

            # now if no scene is running, check if we have a scene to start !!!!
            if self._scene_entity is not None:
                if self.get_state(self._scene_entity) == "scening":    # make sure again, that it's a scene
                    self._last_scene_activated = self._scene_entity    # store for later processing
                    self.turn_on( self._scene_entity )
                    self.log("Scene {} turned on.".format( self._scene_entity ), level="INFO")
                    self._restart_timer_state ="motion scene"
                    self.restart_timer( self._restart_timer_state )
                    return   # stop further processing !!!!!!!!!!!!!!! 

            # we don't have a scene running or had to start one - starting lights !!!!
            else:
                tempStatus='no'
                for light_entity in self._light_entities:
                    light_state = self.get_state( light_entity )
                    if light_state not in ['off', 'on']:
                        self.log("Invalid light state for {}: {}. Expecting either on or off.".format(light_entity,light_state), level="ERROR")
                        # we don't return, because we want to keep it running
          
                    if light_state == "off" and self._restart_timer_state !="motion scene":
                        self.turn_on_light( light_entity )
                        if tempStatus == 'no':
                            tempStatus ='motion light'
                        self._restart_timer_state ="motion light"
                    elif light_state == "on":
                        self.log('Light already ON ({}) - {}'.format(light_entity,self._restart_timer_state) )
                        if self._restart_timer_state == "motion light" or self._restart_timer == "yes":
                            self.log('Light already ON - restart state:{} - type:{}'.format( self._restart_timer_state , self._restart_timer ))
                            if tempStatus == 'no' or tempStatus !='motion light':
                                tempStatus ='just restart'
                if tempStatus !='no':
                    self.restart_timer(self._restart_timer_state)                    


    def stop_timer(self,param):
        if self._countdown_entity is not None:
            self.call_service("timer/cancel", entity_id = self._countdown_entity)
        else:
            self.cancel_timer(self._timer)
        self._restart_timer_state ="-"
        
    def start_timer(self,param):
        if self._countdown_entity is not None:
            self.call_service("timer/start", entity_id  = self._countdown_entity)
            self.log("start_timer {}".format(entity_id) )
        else:
            if param == "motion scene":
                self._timer = self.run_in(self.turn_off_light, self._scene_timeout)
                self.log("start_timer scene timeout:{} - {}".format( self._scene_timeout , param ) )
                self._restart_timer_state=param
            else:
                self._timer = self.run_in(self.turn_off_light, self._light_timeout)
                self.log("start_timer light timeout:{} - {}".format( self._light_timeout, param ) )
                self._restart_timer_state=param

    def restart_timer(self , param ):
        if self.is_motion_sensor_disabled():
            self.log('Timer not restarted because smartlight disabled')
            return
        self.log('Restart timer {}'.format(param) )
        self.stop_timer(param)
        self.start_timer(param)

    def turn_on_light(self,light_entity):
        light_entity_domain = light_entity.split(".")
        if light_entity_domain[0] == "light":
            self.turn_on( light_entity , brightness_pct = self.get_my_brightness()  )
            # self.turn_on( light_entity , brightness_pct = self.get_my_brightness() , transition = self._transition )
            # self.call_service( 'light/turn_on', entity_id = light_entity , brightness_pct = self.get_my_brightness() , transition = self._transition)
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
                self._last_scene_activated='-'
            except (ValueError, TypeError):
                self.log('ERROR in scene shutdown !!' ,level="WARNING")
            
        
