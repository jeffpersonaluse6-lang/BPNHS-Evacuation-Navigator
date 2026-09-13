"""Large draggable drafting window above the campus editor."""
import flet as ft
import inspect


class DraftingWindow:
    def __init__(self,page,editor_factory,on_add):
        self.page=page
        self.on_add=on_add
        self.drag_origin=None
        self.maximized=True
        self.editor=editor_factory(self.add if on_add else None)
        pw,ph=self.page_size()
        self.saved_bounds=(16,12,pw-32,ph-24)
        self.panel=ft.Container(left=0,top=0,width=pw,height=ph,
            bgcolor="#FFFFFF",border=ft.Border.all(1,"#94A3B8"),border_radius=10,
            clip_behavior=ft.ClipBehavior.HARD_EDGE)
        title=ft.GestureDetector(mouse_cursor=ft.MouseCursor.MOVE,drag_interval=16,
            on_pan_start=self.start_move,on_pan_update=self.move,
            content=ft.Container(expand=True,padding=8,
                content=ft.Text("Building drafting editor",color="#FFFFFF",size=15)))
        self.resize_grip=ft.GestureDetector(visible=False,
            mouse_cursor=ft.MouseCursor.RESIZE_DOWN_RIGHT,drag_interval=16,
            on_pan_start=self.start_resize,on_pan_update=self.resize,
            content=ft.Container(height=16,alignment=ft.Alignment.CENTER_RIGHT,
                content=ft.Text("Drag corner to resize  ◢",size=11,color="#64748B")))
        self.panel.content=ft.Column(spacing=0,controls=[
            ft.Container(bgcolor="#12345A",content=ft.Row(spacing=0,controls=[
                ft.Container(expand=True,content=title),
                ft.IconButton(icon=ft.Icons.OPEN_IN_FULL,icon_color="#FFFFFF",tooltip="Maximize / restore",on_click=self.maximize),
                ft.IconButton(icon=ft.Icons.CLOSE,icon_color="#FFFFFF",tooltip="Close drafting window",on_click=self.close)])),
            ft.Container(expand=True,padding=4,content=self.editor.control),
            self.resize_grip,
        ])
        self.overlay=ft.Stack(expand=True,controls=[self.panel])

    def page_size(self):
        return max(320,self.page.width or 1400),max(300,self.page.height or 900)

    def show(self):
        if self.overlay not in self.page.overlay:
            self.page.overlay.append(self.overlay)
            self.editor.shortcuts.install()
            self.previous_resize=getattr(self.page,"on_resize",None)
            self.resize_handler=self.page_resized
            self.page.on_resize=self.resize_handler
        self.page.update()

    def remove(self):
        if self.overlay in self.page.overlay:
            self.page.overlay.remove(self.overlay)
            self.editor.shortcuts.remove()
            if self.page.on_resize==self.resize_handler:
                self.page.on_resize=self.previous_resize
        self.page.update()

    async def page_resized(self,event):
        if self.previous_resize:
            result=self.previous_resize(event)
            if inspect.isawaitable(result):
                await result
        if self.overlay not in self.page.overlay:
            return
        pw,ph=self.page_size()
        if self.maximized:
            self.panel.width,self.panel.height=pw,ph
        else:
            self.panel.width=min(self.panel.width,pw)
            self.panel.height=min(self.panel.height,ph)
            self.panel.left=max(0,min(self.panel.left,pw-180))
            self.panel.top=max(0,min(self.panel.top,ph-80))
        self.page.update()

    def close(self,event=None):
        if self.editor.exporting:
            return
        if self.editor.document.dirty:
            self.editor.confirm("Close drafting editor without saving?",self.remove)
        else:
            self.remove()

    async def add(self,document,floor):
        await self.on_add(document,floor)
        self.remove()

    def start_move(self,event):
        self.drag_origin=(event.global_position.x,event.global_position.y,self.panel.left,self.panel.top)

    def move(self,event):
        if self.drag_origin is None or self.maximized:
            return
        x,y,left,top=self.drag_origin
        pw,ph=self.page_size()
        self.panel.left=max(0,min(pw-180,left+event.global_position.x-x))
        self.panel.top=max(0,min(ph-80,top+event.global_position.y-y))
        self.panel.update()

    def start_resize(self,event):
        self.resize_origin=(event.global_position.x,event.global_position.y,self.panel.width,self.panel.height)

    def resize(self,event):
        if not hasattr(self,'resize_origin') or self.maximized:
            return
        x,y,w,h=self.resize_origin
        pw,ph=self.page_size()
        self.panel.width=max(min(700,pw),min(pw,w+event.global_position.x-x))
        self.panel.height=max(min(480,ph),min(ph,h+event.global_position.y-y))
        self.panel.update()

    def maximize(self,event=None):
        if self.maximized:
            self.panel.left,self.panel.top,self.panel.width,self.panel.height=self.saved_bounds
            pw,ph=self.page_size()
            self.panel.width,self.panel.height=min(self.panel.width,pw),min(self.panel.height,ph)
            self.panel.left=max(0,min(self.panel.left,pw-180))
            self.panel.top=max(0,min(self.panel.top,ph-80))
        else:
            self.saved_bounds=(self.panel.left,self.panel.top,self.panel.width,self.panel.height)
            self.panel.left=self.panel.top=0
            self.panel.width,self.panel.height=self.page_size()
        self.maximized=not self.maximized
        self.resize_grip.visible=not self.maximized
        self.panel.update()

