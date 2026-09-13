"""An explicit map transform with frame-independent, bounded camera following."""

from dataclasses import dataclass
import math
import flet as ft


@dataclass
class SmoothCamera:
    width: float = 1368
    height: float = 710
    x: float = 0
    y: float = 0
    scale: float = 1
    rotation: float = 0

    def screen(self,point):
        c,s=math.cos(self.rotation),math.sin(self.rotation)
        return (self.x+self.scale*(c*point[0]-s*point[1]),
                self.y+self.scale*(s*point[0]+c*point[1]))

    def world(self,point):
        x,y=(point[0]-self.x)/self.scale,(point[1]-self.y)/self.scale
        c,s=math.cos(self.rotation),math.sin(self.rotation)
        return c*x+s*y,-s*x+c*y

    def center(self,point):
        sx,sy=self.screen(point)
        self.x+=self.width/2-sx;self.y+=self.height/2-sy

    def visible(self,point,diameter=20):
        x,y=self.screen(point)
        margin=diameter*self.scale/2+16
        return margin<=x<=self.width-margin and margin<=y<=self.height-margin

    def follow(self,point,dt,*,moving=False,diameter=20,guard=None):
        """Only translate: preserve zoom, rotation and all authored geometry."""
        if dt<=0:return False
        sx,sy=self.screen(point)
        ex,ey=self.width/2-sx,self.height/2-sy
        before=(self.x,self.y)
        margin=diameter*self.scale/2+24
        limits=(max(0,self.width/2-margin),max(0,self.height/2-margin))
        visible=self.visible(point,diameter)
        guard=visible if guard is None else guard
        rate=5 if moving else 7
        if guard:
            # Catch up sooner near the viewport edge before the safety guard
            # needs to intervene. Normal movement retains a soft trailing gap.
            urgency=max(abs(ex)/max(1,limits[0]),abs(ey)/max(1,limits[1]))
            rate+=12*max(0,urgency-.65)**2
        alpha=-math.expm1(-rate*dt)
        self.x+=ex*alpha;self.y+=ey*alpha
        if guard:
            # A large movement step/window resize must never push a visible
            # player out of view. An offscreen manual view recenters gradually.
            px,py=self.screen(point)
            self.x+=max(-limits[0],min(limits[0],px-self.width/2))-(px-self.width/2)
            self.y+=max(-limits[1],min(limits[1],py-self.height/2))-(py-self.height/2)
        if math.hypot(ex,ey)<.05:self.x+=ex*(1-alpha);self.y+=ey*(1-alpha)
        return math.hypot(self.x-before[0],self.y-before[1])>1e-6


class CameraViewport(ft.GestureDetector):
    """Retain the world canvas and apply camera transforms to its root only.

    Owning the transform avoids native viewer inertia/clamping silently changing
    the camera state. Gestures and following therefore share exact coordinates.
    """
    def __init__(self,scene,point,*,width=1368,height=710):
        self.camera=SmoothCamera(width,height)
        self.camera.center(point)
        self.scene=scene
        self.scene.left=self.scene.top=0
        self.pan_enabled=True
        self.scale_enabled=True
        self.min_scale=.6;self.max_scale=3
        self.gesture_anchor=None
        self.on_manual=None
        self.gesture_scale=1;self.gesture_rotation=0
        self.apply(False)
        super().__init__(expand=True,drag_interval=16,trackpad_scroll_causes_scale=True,
            content=ft.Stack(expand=True,clip_behavior=ft.ClipBehavior.HARD_EDGE,controls=[scene]),
            on_scale_start=self.start,on_scale_update=self.gesture_update,on_scale_end=self.end,
            on_scroll=self.scroll,on_size_change=self.resize)

    def apply(self,update=True):
        camera=self.camera
        self.scene.transform=ft.Transform(matrix=ft.Matrix4.identity().translate(camera.x,camera.y)
            .rotate_z(camera.rotation).scale(camera.scale,camera.scale))
        if update:self.scene.update()

    def resize(self,event):
        if event.width<=0 or event.height<=0:return
        # Preserve the current view center on layout changes, including headers
        # and mobile windows. Use the actual viewport, not guessed page padding.
        self.camera.x+=(event.width-self.camera.width)/2
        self.camera.y+=(event.height-self.camera.height)/2
        self.camera.width=event.width;self.camera.height=event.height
        self.apply()

    def start(self,event):
        if not self.pan_enabled and not self.scale_enabled:return
        if self.on_manual:self.on_manual()
        self.gesture_anchor=self.camera.world((event.local_focal_point.x,event.local_focal_point.y))
        self.gesture_scale=self.camera.scale;self.gesture_rotation=self.camera.rotation

    def gesture_update(self,event):
        if self.gesture_anchor is None or (not self.pan_enabled and not self.scale_enabled):return
        if self.scale_enabled:
            self.camera.scale=max(self.min_scale,min(self.max_scale,self.gesture_scale*event.scale))
            self.camera.rotation=self.gesture_rotation+event.rotation
        focal=(event.local_focal_point.x,event.local_focal_point.y)
        current=self.camera.screen(self.gesture_anchor)
        if self.pan_enabled or self.scale_enabled:
            self.camera.x+=focal[0]-current[0];self.camera.y+=focal[1]-current[1]
        self.apply()

    def end(self,event=None):self.gesture_anchor=None

    def scroll(self,event):
        if not self.scale_enabled:return
        if self.on_manual:self.on_manual()
        anchor=(event.local_position.x,event.local_position.y)
        self.change_zoom(math.exp(max(-2,min(2,-event.scroll_delta.y/200))),anchor)

    def change_zoom(self,factor,anchor):
        world=self.camera.world(anchor)
        self.camera.scale=max(self.min_scale,min(self.max_scale,self.camera.scale*factor))
        current=self.camera.screen(world)
        self.camera.x+=anchor[0]-current[0];self.camera.y+=anchor[1]-current[1]
        self.apply()

    async def zoom(self,factor):self.change_zoom(factor,(self.camera.width/2,self.camera.height/2))

    async def pan(self,dx,dy=0):
        self.camera.x+=dx;self.camera.y+=dy;self.apply()

    async def reset(self):
        self.camera.scale=1;self.camera.rotation=0;self.camera.x=self.camera.y=0;self.apply()

    def follow(self,point,dt,*,moving=False,diameter=20,guard=None):
        changed=self.camera.follow(point,dt,moving=moving,diameter=diameter,guard=guard)
        if changed:self.apply()
        return changed
