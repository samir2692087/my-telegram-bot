import json
import logging
import io
import os # <-- This is important
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from PIL import Image

# --- Configuration ---
# --- THIS IS THE ONLY LINE THAT CHANGED ---
# We are now using a simpler variable name to ensure it works.
BOT_TOKEN = os.getenv("8199651093:AAGpq3dbYFSFENDzlJmMEh9ld-Ua3ZOmrdo")

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Constants ---
SELECT_ACTION, GET_PIXELS, GET_CM, GET_KB = range(4)
DPI = 96

# --- Bot Functions (No changes needed in the functions below) ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Hello! I am your Image Resizer Bot.\n\n"
        "To get started, simply send me any image you want to resize."
    )

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message.photo:
        await update.message.reply_text("Please send me an image file.")
        return ConversationHandler.END

    await update.message.reply_text("Image received! I'm downloading it now...")

    try:
        photo_file = await update.message.photo[-1].get_file()
        image_bytes_io = io.BytesIO()
        await photo_file.download_to_memory(image_bytes_io)
        image_bytes_io.seek(0)
        context.user_data['image_bytes'] = image_bytes_io
    except Exception as e:
        logger.error(f"Error downloading photo: {e}")
        await update.message.reply_text("Sorry, I had trouble downloading the image. Please try again.")
        return ConversationHandler.END
    
    keyboard = [
        [InlineKeyboardButton("Resize by Pixels (e.g., 800x600)", callback_data=str(GET_PIXELS))],
        [InlineKeyboardButton("Resize by Centimeters (e.g., 10x15)", callback_data=str(GET_CM))],
        [InlineKeyboardButton("Resize by File Size (e.g., 500 KB)", callback_data=str(GET_KB))],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("How would you like to resize this image?", reply_markup=reply_markup)
    return SELECT_ACTION

async def select_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    choice = int(query.data)
    context.user_data['choice'] = choice

    if choice == GET_PIXELS:
        await query.edit_message_text(
            text="Please enter dimensions in pixels: `width x height` \\(e\\.g\\., `1920 x 1080`\\)",
            parse_mode='MarkdownV2'
        )
        return GET_PIXELS
    elif choice == GET_CM:
        await query.edit_message_text(
            text="Please enter dimensions in cm: `width x height` \\(e\\.g\\., `10 x 15`\\)",
            parse_mode='MarkdownV2'
        )
        return GET_CM
    elif choice == GET_KB:
        await query.edit_message_text(
            text="Please enter target file size in KB: `500`",
            parse_mode='MarkdownV2'
        )
        return GET_KB
    else:
        await query.edit_message_text(text="Sorry, an invalid option was selected.")
        return ConversationHandler.END

async def get_pixels(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        dims_text = update.message.text.lower().split('x')
        width = int(dims_text[0].strip())
        height = int(dims_text[1].strip())
        await update.message.reply_text(f"Resizing to {width}x{height} pixels...")
        image_bytes = context.user_data['image_bytes']
        img = Image.open(image_bytes)
        resized_img = img.resize((width, height), Image.Resampling.LANCZOS)
        await send_resized_image(update, context, resized_img, "resized_pixels.png")
    except (ValueError, IndexError):
        await update.message.reply_text("Invalid format. Please use `width x height`, e.g., `800 x 600`.")
        return GET_PIXELS
    except Exception as e:
        logger.error(f"Error in get_pixels: {e}")
        await update.message.reply_text("An unexpected error occurred.")
    return ConversationHandler.END

async def get_cm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        dims_text = update.message.text.lower().split('x')
        cm_width = float(dims_text[0].strip())
        cm_height = float(dims_text[1].strip())
        px_width = int((cm_width / 2.54) * DPI)
        px_height = int((cm_height / 2.54) * DPI)
        await update.message.reply_text(f"Converting to {px_width}x{px_height} pixels and resizing...")
        image_bytes = context.user_data['image_bytes']
        img = Image.open(image_bytes)
        resized_img = img.resize((px_width, px_height), Image.Resampling.LANCZOS)
        await send_resized_image(update, context, resized_img, "resized_cm.png")
    except (ValueError, IndexError):
        await update.message.reply_text("Invalid format. Please use `width x height`, e.g., `10.5 x 15`.")
        return GET_CM
    except Exception as e:
        logger.error(f"Error in get_cm: {e}")
        await update.message.reply_text("An unexpected error occurred.")
    return ConversationHandler.END

async def get_kb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        target_kb = int(update.message.text.strip())
        target_bytes = target_kb * 1024
        await update.message.reply_text(f"Attempting to resize to under {target_kb} KB...")
        image_bytes = context.user_data['image_bytes']
        img = Image.open(image_bytes)
        if img.mode == 'RGBA': img = img.convert('RGB')
        quality = 95
        current_ratio = 1.0
        for _ in range(20):
            output_buffer = io.BytesIO()
            new_width, new_height = int(img.width * current_ratio), int(img.height * current_ratio)
            if new_width == 0 or new_height == 0: break
            temp_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            temp_img.save(output_buffer, format='JPEG', quality=quality)
            if output_buffer.tell() <= target_bytes:
                await update.message.reply_text(f"Success! Resized to {output_buffer.tell() // 1024} KB.")
                await send_resized_image(update, context, temp_img, "resized_kb.jpg", is_buffer=True, buffer=output_buffer)
                return ConversationHandler.END
            if output_buffer.tell() > target_bytes * 1.5: current_ratio *= 0.8
            else: quality -= 5
            if quality < 10: break
        await update.message.reply_text(f"Sorry, I couldn't resize the image to be under {target_kb} KB.")
    except ValueError:
        await update.message.reply_text("Invalid format. Please enter a number, e.g., `500`.")
        return GET_KB
    except Exception as e:
        logger.error(f"Error in get_kb: {e}")
        await update.message.reply_text("An unexpected error occurred.")
    return ConversationHandler.END

async def send_resized_image(update: Update, context: ContextTypes.DEFAULT_TYPE, img: Image, filename: str, is_buffer=False, buffer=None):
    try:
        if not is_buffer:
            output_buffer = io.BytesIO()
            fmt = 'PNG' if filename.endswith('.png') else 'JPEG'
            if fmt == 'JPEG' and img.mode == 'RGBA': img = img.convert('RGB')
            img.save(output_buffer, format=fmt)
            output_buffer.seek(0)
        else:
            output_buffer = buffer
            output_buffer.seek(0)
        await context.bot.send_document(
            chat_id=update.effective_chat.id, document=output_buffer, filename=filename, caption="Here is your resized image."
        )
    except Exception as e:
        logger.error(f"Error sending resized image: {e}")
        await update.message.reply_text("Sorry, there was an error sending the final image.")
    finally:
        context.user_data.clear()

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Operation cancelled.")
    context.user_data.clear()
    return ConversationHandler.END

def main() -> None:
    # --- THIS IS THE NEW DEBUGGING CODE ---
    print("--- START OF ENVIRONMENT VARIABLES ---")
    print(json.dumps(dict(os.environ),indent=2))
    print("--- END OF ENVIRONMENT VARIABLES ---")
    """Set up and run the bot."""
    if not BOT_TOKEN:
        # This is the error message that will appear in the logs if the token is not found
        logger.error("FATAL: BOT_TOKEN environment variable not set.")
        return

    application = (
        Application.builder().token(BOT_TOKEN).connect_timeout(30).read_timeout(30).build()
    )

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.PHOTO, photo_handler)],
        states={
            SELECT_ACTION: [CallbackQueryHandler(select_action)],
            GET_PIXELS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_pixels)],
            GET_CM: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_cm)],
            GET_KB: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_kb)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("cancel", cancel))

    print("Bot is running...")
    application.run_polling()

if __name__ == "__main__":
    main()

