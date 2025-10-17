import sys
import os
import bpy
import bpy.props
import re
from .utilities import *

bl_info = {
    "name": "GPT-4 Blender Assistant",
    "blender": (2, 82, 0),
    "category": "Object",
    "author": "Aarya (@gd3kr), adapted for the new OpenAi api project by @Shinanubis",
    "version": (3, 0, 0),
    "location": "3D View > UI > GPT-4 Blender Assistant",
    "description": "Generate Blender Python code using OpenAI's GPT-4 API (Project Key compatible).",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
}

system_prompt = """You are an assistant made for the purposes of helping the user with Blender, the 3D software.
- Respond with your answers in markdown (```). 
- Preferably import entire modules instead of bits.
- Do not perform destructive operations on the meshes.
- Do not use cap_ends. Do not do more than what is asked (setting up render settings, adding cameras, etc.)
- Do not respond with anything that is not Python code.

Example:

import bpy
bpy.ops.mesh.primitive_cube_add(location=(0,0,0))
```"""



# ======================================================================================
# CLASSES
# ======================================================================================

class GPT4_OT_DeleteMessage(bpy.types.Operator):
    bl_idname = "gpt4.delete_message"
    bl_label = "Delete Message"
    message_index: bpy.props.IntProperty()

    def execute(self, context):
        context.scene.gpt4_chat_history.remove(self.message_index)
        return {'FINISHED'}


class GPT4_OT_ShowCode(bpy.types.Operator):
    bl_idname = "gpt4.show_code"
    bl_label = "Show Code"
    code: bpy.props.StringProperty(default="")

    def execute(self, context):
        text_name = "GPT4_Generated_Code.py"
        text = bpy.data.texts.get(text_name) or bpy.data.texts.new(text_name)
        text.clear()
        text.write(self.code)
        for area in context.screen.areas:
            if area.type == 'TEXT_EDITOR':
                area.spaces.active.text = text
                return {'FINISHED'}
        return {'FINISHED'}


class GPT4_PT_Panel(bpy.types.Panel):
    bl_label = "GPT-4 Blender Assistant"
    bl_idname = "GPT4_PT_Panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'GPT-4 Assistant'

    def draw(self, context):
        layout = self.layout
        column = layout.column(align=True)

        column.label(text="Chat history:")
        box = column.box()
        for index, message in enumerate(context.scene.gpt4_chat_history):
            row = box.row()
            if message.type == 'assistant':
                row.label(text="Assistant:")
                op = row.operator("gpt4.show_code", text="Show Code")
                op.code = message.content
            else:
                row.label(text=f"User: {message.content}")
            del_op = row.operator("gpt4.delete_message", text="", icon="TRASH", emboss=False)
            del_op.message_index = index

        column.separator()
        column.label(text="Model:")
        column.prop(context.scene, "gpt4_model", text="")
        column.label(text="Your message:")
        column.prop(context.scene, "gpt4_chat_input", text="")
        row = column.row(align=True)
        row.operator("gpt4.send_message", text="Execute")
        row.operator("gpt4.clear_chat", text="Clear Chat")


# ======================================================================================
# BUTTON "CLEAR"
# ======================================================================================

class GPT4_OT_ClearChat(bpy.types.Operator):
    bl_idname = "gpt4.clear_chat"
    bl_label = "Clear Chat"

    def execute(self, context):
        context.scene.gpt4_chat_history.clear()
        return {'FINISHED'}


# ======================================================================================
# EXEC OPENAI REQUEST
# ======================================================================================

class GPT4_OT_Execute(bpy.types.Operator):
    bl_idname = "gpt4.send_message"
    bl_label = "Send Message"

    def execute(self, context):
        prefs = bpy.context.preferences.addons[__name__].preferences
        os.environ["OPENAI_API_KEY"] = prefs.api_key
        os.environ["OPENAI_PROJECT"] = prefs.project_id
        os.environ["OPENAI_ORGANIZATION"] = prefs.organization_id

        context.scene.gpt4_button_pressed = True
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)

        blender_code = generate_blender_code(
            context.scene.gpt4_chat_input,
            context.scene.gpt4_chat_history,
            context,
            system_prompt,
        )

        message = context.scene.gpt4_chat_history.add()
        message.type = 'user'
        message.content = context.scene.gpt4_chat_input
        context.scene.gpt4_chat_input = ""

        if blender_code:
            msg = context.scene.gpt4_chat_history.add()
            msg.type = 'assistant'
            msg.content = blender_code
            try:
                exec(blender_code, globals().copy())
            except Exception as e:
                self.report({'ERROR'}, f"Execution error: {e}")
        else:
            self.report({'ERROR'}, "No code generated.")

        context.scene.gpt4_button_pressed = False
        return {'FINISHED'}


# ======================================================================================
# TEST OPENAI CONNEXION
# ======================================================================================

class GPT4_OT_TestConnection(bpy.types.Operator):
    """Test and save OpenAI API connection"""
    bl_idname = "gpt4.test_connection"
    bl_label = "Test OpenAI Connection"

    def execute(self, context):
        from openai import OpenAI
        prefs = bpy.context.preferences.addons[__name__].preferences

        api_key = prefs.api_key.strip()
        project = prefs.project_id.strip()
        org = prefs.organization_id.strip()

        if not api_key or not project:
            self.report({'ERROR'}, "❌ Please enter both API key and Project ID before testing.")
            return {'CANCELLED'}

        try:
            client = OpenAI(
                api_key=api_key,
                project=project,
                organization=org if org else None
            )
            models = client.models.list()

            # ✅ If success: save values to preferences
            prefs.api_key = api_key
            prefs.project_id = project
            prefs.organization_id = org
            bpy.ops.wm.save_userpref()  # Persist preferences automatically

            self.report({'INFO'}, f"✅ Connection successful! {len(models.data)} models available.")
            print(f"[BlenderGPT] ✅ OpenAI connection successful for project: {project}")
            return {'FINISHED'}

        except Exception as e:
            error_msg = str(e).split(":")[-1].strip()
            self.report({'ERROR'}, f"❌ Connection failed: {error_msg}")
            print(f"[BlenderGPT] ❌ OpenAI connection failed: {e}")
            return {'CANCELLED'}



# ======================================================================================
# PREFERENCES ADDON
# ======================================================================================

class GPT4AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    api_key: bpy.props.StringProperty(
        name="OpenAI API Key",
        description="Your OpenAI API key (starts with sk-proj-...)",
        default="",
        #subtype="PASSWORD",
    )
    project_id: bpy.props.StringProperty(
        name="Project ID",
        description="Your OpenAI Project ID (starts with proj_...)",
        default="",
    )
    organization_id: bpy.props.StringProperty(
        name="Organization ID",
        description="Your OpenAI Organization ID (starts with org_...)",
        default="",
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "api_key")
        layout.prop(self, "project_id")
        layout.prop(self, "organization_id")
        layout.separator()
        layout.operator("gpt4.test_connection", icon="NETWORK_DRIVE", text="Test connexion")
        layout.label(text="⚙️ Enter OpenAI informations on top.")


# ======================================================================================
# REGISTER / UNREGISTER
# ======================================================================================

def register():
    bpy.utils.register_class(GPT4AddonPreferences)
    bpy.utils.register_class(GPT4_OT_Execute)
    bpy.utils.register_class(GPT4_PT_Panel)
    bpy.utils.register_class(GPT4_OT_ClearChat)
    bpy.utils.register_class(GPT4_OT_ShowCode)
    bpy.utils.register_class(GPT4_OT_DeleteMessage)
    bpy.utils.register_class(GPT4_OT_TestConnection)
    bpy.types.VIEW3D_MT_mesh_add.append(lambda s, c: s.layout.operator(GPT4_OT_Execute.bl_idname))
    init_props()


def unregister():
    bpy.utils.unregister_class(GPT4AddonPreferences)
    bpy.utils.unregister_class(GPT4_OT_Execute)
    bpy.utils.unregister_class(GPT4_PT_Panel)
    bpy.utils.unregister_class(GPT4_OT_ClearChat)
    bpy.utils.unregister_class(GPT4_OT_ShowCode)
    bpy.utils.unregister_class(GPT4_OT_DeleteMessage)
    bpy.utils.unregister_class(GPT4_OT_TestConnection)
    bpy.types.VIEW3D_MT_mesh_add.remove(lambda s, c: s.layout.operator(GPT4_OT_Execute.bl_idname))
    clear_props()


if __name__ == "__main__":
    register()
