"""Session clipboard metadata and destination-floor rebinding, not runtime state."""

from dataclasses import dataclass,replace


@dataclass(frozen=True)
class SelectionClipboard:
    roots: tuple
    floors: dict
    source_scope: str
    source_parent_id: str | None

    @property
    def on_floor(self):return self.source_parent_id is not None


def floor_number(scope):
    return int(scope.split()[-1]) if ":Floor " in scope else None


def rebind_floor_items(originals,copies,clipboard,destination,parent):
    """Keep geometry; clone attachments within the bundle and retarget stairs.

    A missing destination disables that stair, never discards an entire layout.
    The original bundle is immutable and can be pasted onto another floor later.
    """
    source=floor_number(clipboard.source_scope);target=floor_number(destination)
    adjusted=[];disabled=0
    for original,item in zip(originals,copies):
        changes={}
        if original.parent_id==clipboard.source_parent_id:changes["parent_id"]=parent.id
        if item.kind=="stairs":
            changes["stair_from"]=target
            if target is None:
                changes.update(stair_enabled=False,stair_to=None)
            else:
                offset=target-(item.stair_from or source or target)
                to=item.stair_to+offset if item.stair_to is not None else None
                if to is not None and (not 1<=to<=parent.floor_count or to==target or
                        (item.stair_direction=="up")!=(to>target)):
                    changes.update(stair_enabled=False,stair_to=None);disabled+=1
                else:changes["stair_to"]=to
        adjusted.append(replace(item,**changes))
    return adjusted,disabled
