import sys
import os
import bpy
import bpy.props
import re

# ==============================================================
# Load the bundled OpenAI dependency from /lib
# ==============================================================
libs_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "lib")
if libs_path not in sys.path:
    sys.path.append(libs_path)

try:
    from openai import OpenAI
except ImportError as e:
    print(f"❌ Failed to import OpenAI module from {libs_path}: {e}")
    raise e

from .utilities import *

# ==============================================================
# Addon metadata
# ==============================================================
bl_info = {
    "name": "GPT-4 Blender Assistant",
    "blender": (2, 82, 0),
    "category": "Object",
    "author": "Aarya (@gd3kr) + ChatGPT integration by Eric Maginot",
    "version": (3, 3, 0),
    "location": "3D View > UI > GPT-4 Assistant",
    "description": "Generate Blender Python code using OpenAI GPT models.",
}

# ==============================================================
# System prompt for GPT
# ==============================================================
system_prompt = """You are an assistant made for Blender, the 3D software.
Respond only with valid Python code inside triple backticks (```).
Avoid destructive operations, do not add cameras or lights unless asked.
Example:

import bpy
bpy.ops.mesh.primitive_cube_add(location=(0,0,0))
```"""

# ==============================================================
# Operator: Delete chat messages
# ==============================================================
class GPT4_OT_DeleteMessage(bpy.types.Operator):
    bl_idname = "gpt4.delete_message"
    bl_label = "Delete Message"
    message_index: bpy.props.IntProperty()

    def execute(self, context):
        context.scene.gpt4_chat_history.remove(self.message_index)
        return {'FINISHED'}


# ==============================================================
# Operator: Show generated code in Blender text editor
# ==============================================================
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


# ==============================================================
# Operator: Clear chat history
# ==============================================================
class GPT4_OT_ClearChat(bpy.types.Operator):
    bl_idname = "gpt4.clear_chat"
    bl_label = "Clear Chat"

    def execute(self, context):
        context.scene.gpt4_chat_history.clear()
        return {'FINISHED'}


# ==============================================================
# Operator: Execute GPT request
# ==============================================================
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

        msg_user = context.scene.gpt4_chat_history.add()
        msg_user.type = 'user'
        msg_user.content = context.scene.gpt4_chat_input
        context.scene.gpt4_chat_input = ""

        if blender_code:
            msg_ai = context.scene.gpt4_chat_history.add()
            msg_ai.type = 'assistant'
            msg_ai.content = blender_code
            try:
                exec(blender_code, globals().copy())
            except Exception as e:
                self.report({'ERROR'}, f"Execution error: {e}")
        else:
            self.report({'ERROR'}, "No code generated.")

        context.scene.gpt4_button_pressed = False
        return {'FINISHED'}


# ==============================================================
# Operator: Test and save OpenAI connection
# ==============================================================
class GPT4_OT_TestConnection(bpy.types.Operator):
    """Test and save OpenAI API connection"""
    bl_idname = "gpt4.test_connection"
    bl_label = "Test OpenAI Connection"

    def execute(self, context):
        prefs = bpy.context.preferences.addons[__name__].preferences
        api_key, project, org = prefs.api_key.strip(), prefs.project_id.strip(), prefs.organization_id.strip()

        if not api_key or not project:
            self.report({'ERROR'}, "❌ Please enter both API key and Project ID before testing.")
            return {'CANCELLED'}

        try:
            client = OpenAI(api_key=api_key, project=project, organization=org if org else None)
            models = client.models.list()

            # ✅ Save credentials permanently
            prefs.api_key = api_key
            prefs.project_id = project
            prefs.organization_id = org
            bpy.ops.wm.save_userpref()

            self.report({'INFO'}, f"✅ Connection successful! {len(models.data)} models available.")
            print(f"[BlenderGPT] ✅ Connected to OpenAI project: {project}")
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"❌ Connection failed: {str(e)}")
            print(f"[BlenderGPT] ❌ Connection failed: {e}")
            return {'CANCELLED'}


# ==============================================================
# Addon Preferences UI
# ==============================================================
class GPT4AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    api_key: bpy.props.StringProperty(
        name="OpenAI API Key",
        description="Your OpenAI API key (starts with sk-proj-...)",
        default="",
        subtype="PASSWORD",
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
        layout.operator("gpt4.test_connection", icon="NETWORK_DRIVE", text="Test Connection")
        layout.label(text="⚙️ Enter your OpenAI credentials above.")


# ==============================================================
# Main Panel (3D View)
# ==============================================================
class GPT4_PT_Panel(bpy.types.Panel):
    bl_label = "GPT-4 Blender Assistant"
    bl_idname = "GPT4_PT_Panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'GPT-4 Assistant'

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)

        col.label(text="Chat history:")
        box = col.box()
        for i, msg in enumerate(context.scene.gpt4_chat_history):
            row = box.row()
            if msg.type == 'assistant':
                row.label(text="Assistant:")
                op = row.operator("gpt4.show_code", text="Show Code")
                op.code = msg.content
            else:
                row.label(text=f"User: {msg.content}")
            del_op = row.operator("gpt4.delete_message", text="", icon="TRASH", emboss=False)
            del_op.message_index = i

        col.separator()
        col.label(text="Model:")
        col.prop(context.scene, "gpt4_model", text="")
        col.label(text="Your message:")
        col.prop(context.scene, "gpt4_chat_input", text="")
        row = col.row(align=True)
        row.operator("gpt4.send_message", text="Execute")
        row.operator("gpt4.clear_chat", text="Clear Chat")


# ==============================================================
# Register / Unregister
# ==============================================================
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
