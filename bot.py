import os
import json
import logging
from uuid import uuid4
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes, ConversationHandler
from telegram.error import TelegramError
from config import TOKEN, ADMIN_CHAT_ID
from PIL import Image
import io

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

LANGUAGES = ["Azərbaycan", "İngilis", "Rus"]

# Conversation States
(UPLOAD_SLIDE, UPLOAD_NAME, UPLOAD_CATEGORY, UPLOAD_PRICE, UPLOAD_CARD,
 UPLOAD_IMAGE, UPLOAD_LANGUAGE, UPLOAD_PAGES, SEARCH_TYPE, SEARCH_CATEGORY, 
 SELECT_SLIDE, CONFIRM_PAYMENT, SEARCH_OTHER_CATEGORY, SEARCH_LANGUAGE,
 MY_SLIDES, SELECT_SLIDE_ACTION, EDIT_FIELD, EDIT_VALUE) = range(18)



DB_FILE = "db.json"

# Məşhur dərs kateqoriyaları
CATEGORIES = [
    "IT", "Riyaziyyat", "Elektronika", "English", "Biznes və İdarəetmə",
    "İqtisadiyyat", "Dizayn", "Memarlıq", "Neft-Qaz", "Dilçilik",
    "Tibb", "Tarix", "Hüquq", "SƏTƏMM", "Digər"
]

def load_slides():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                slides = json.load(f)
                # Ensure each slide has a sales field
                for slide in slides:
                    if 'sales' not in slide:
                        slide['sales'] = 0
                return slides
        except json.JSONDecodeError:
            logger.error("Error decoding db.json. Creating empty database.")
            return []
    return []



def save_slide(slide):
    # Ensure file extension exists
    if 'file_extension' not in slide:
        slide['file_extension'] = os.path.splitext(slide['file'])[1].lower()
    if 'file_type' not in slide:
        slide['file_type'] = {
            '.pdf': 'application/pdf',
            '.ppt': 'application/vnd.ms-powerpoint',
            '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
        }.get(slide['file_extension'], 'application/pdf')
    
    slides = load_slides()
    slides.append(slide)
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(slides, f, indent=2, ensure_ascii=False)

# -- Error Handler --
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")
    if update and (update.message or update.callback_query):
        reply_func = update.message.reply_text if update.message else update.callback_query.message.reply_text
        await reply_func("Xəta baş verdi. Zəhmət olmasa yenidən cəhd edin və ya @UniSlayd ilə əlaqə saxlayın.")

# -- Start Command --
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        user = update.message.from_user
        chat_id = update.message.chat_id
        reply_func = update.message.reply_text
    elif update.callback_query:
        user = update.callback_query.from_user
        chat_id = update.callback_query.message.chat_id
        reply_func = update.callback_query.message.reply_text
    else:
        logger.error("No valid message or callback query found in update")
        return ConversationHandler.END

    logger.info(f"User {user.id} ({user.full_name}) started the bot")
    
    context.user_data.clear()
    
    keyboard = [
        [InlineKeyboardButton("📤 Slayd yüklə", callback_data='upload')],
        [InlineKeyboardButton("🔍 Slayd axtar", callback_data='search')]
    ]
    
    await reply_func(
        f"Salam {user.first_name}! UniSlayd botuna xoş gəlmisiniz!\n\n"
        "Bu bot vasitəsilə universitet təqdimatlarını paylaşa və ya axtara bilərsiniz.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ConversationHandler.END

# -- Handle Initial Choice --
async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    
    if query.data == 'upload':
        logger.info(f"User {user.id} ({user.full_name}) selected upload option")
        await query.message.reply_text(
        "Zəhmət olmasa slayd faylını göndər (max 30MB):\n"
        "Dəstəklənən formatlar: PDF, PPT, PPTX\n"
        "İstənilən vaxt /cancel yazaraq əməliyyatı ləğv edə bilərsiniz."
        )
        return UPLOAD_SLIDE
    elif query.data == 'search':
        logger.info(f"User {user.id} ({user.full_name}) selected search option")
        keyboard = [
            [InlineKeyboardButton("📛 Ad ilə axtar", callback_data='search_by_name')],
            [InlineKeyboardButton("📚 Kateqoriya ilə axtar", callback_data='search_by_category')],
            [InlineKeyboardButton("🌐 Dilə görə axtar", callback_data='search_by_language')]
        ]
        await query.message.reply_text(
        "Axtarış üsulunu seçin:\n"
        "İstənilən vaxt /cancel yazaraq əməliyyatı ləğv edə bilərsiniz.",
        reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SEARCH_TYPE

# -- Cancel Command --
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    logger.info(f"User {user.id} ({user.full_name}) canceled the operation")
    
    await update.message.reply_text(
        "Əməliyyat ləğv edildi. Yenidən başlamaq üçün /start əmrini istifadə edə bilərsiniz.",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

# -- Upload Flow --
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    
    if not update.message.document:
        await update.message.reply_text("Zəhmət olmasa PDF və ya PowerPoint faylı göndərin.")
        return UPLOAD_SLIDE
    
    document = update.message.document
    mime_type = document.mime_type
    
    # Dəstəklənən MIME tipləri
    supported_types = {
        'application/pdf': '.pdf',
        'application/vnd.ms-powerpoint': '.ppt',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation': '.pptx'
    }
    
    if mime_type not in supported_types:
        await update.message.reply_text(
            "Yalnız PDF və PowerPoint (PPT/PPTX) faylları dəstəklənir.\n"
            "Zəhmət olmasa düzgün formatda fayl göndərin."
        )
        return UPLOAD_SLIDE
    
    if document.file_size > 30 * 1024 * 1024:  # 30MB
        await update.message.reply_text("Fayl həcmi 30MB-dan böyükdür. Zəhmət olmasa daha kiçik fayl göndərin.")
        return UPLOAD_SLIDE

    logger.info(f"User {user.id} ({user.full_name}) uploaded file: {document.file_name} ({mime_type})")
    
    try:
        # Faylın orijinal adını və genişlənməsini saxla
        original_filename = document.file_name
        file_extension = os.path.splitext(original_filename)[1].lower()
        
        if file_extension not in ['.pdf', '.ppt', '.pptx']:
           file_extension = supported_types[mime_type]
        # Əgər faylın genişlənməsi təkrarlanırsa, onu təmizlə
        if original_filename.lower().endswith(file_extension + file_extension):
            original_filename = original_filename[:-len(file_extension)]
        elif not original_filename.lower().endswith(file_extension):
            original_filename = original_filename + file_extension
        
        
        # Yeni fayl adı yarat
        filename = f"{uuid4()}_{original_filename}"
        file_path = os.path.join("downloads", filename)
        
        logger.debug(f"Saving slide file to: {file_path}")
        
        # Faylı yüklə
        file = await document.get_file()
        await file.download_to_drive(file_path)
        
        # Faylın düzgün yükləndiyini yoxla
        if not os.path.exists(file_path):
            raise Exception(f"Failed to save file: {file_path}")
        
        context.user_data['slide_file'] = file_path
        context.user_data['file_type'] = mime_type
        context.user_data['file_extension'] = file_extension
        
        await update.message.reply_text("Slaydın adını daxil et:")
        return UPLOAD_NAME
        
    except TelegramError as e:
        logger.error(f"Error downloading file: {e}")
        await update.message.reply_text("Fayl yüklənərkən xəta baş verdi. Zəhmət olmasa yenidən cəhd edin.")
        return UPLOAD_SLIDE
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        await update.message.reply_text("Xəta baş verdi. Zəhmət olmasa yenidən cəhd edin.")
        return UPLOAD_SLIDE

async def handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    name = update.message.text.strip()
    
    if not name:
        await update.message.reply_text("Adı boş ola bilməz. Zəhmət olmasa slaydın adını daxil et:")
        return UPLOAD_NAME
    
    logger.info(f"User {user.id} entered slide name: {name}")
    context.user_data['name'] = name
    
    # Kateqoriyaları 3 sütun x 5 sətir formatında göstər
    keyboard = []
    for i in range(0, len(CATEGORIES), 3):
        row = [
            InlineKeyboardButton(CATEGORIES[j], callback_data=f"category_{CATEGORIES[j]}")
            for j in range(i, min(i + 3, len(CATEGORIES)))
        ]
        keyboard.append(row)
    
    await update.message.reply_text(
        "Slaydın kateqoriyasını seçin:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return UPLOAD_CATEGORY

async def handle_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    category = query.data.replace("category_", "")
    
    if category == "Digər":
        await query.message.reply_text("Zəhmət olmasa kateqoriya adını daxil edin:")
        return UPLOAD_CATEGORY
    else:
        logger.info(f"User {query.from_user.id} selected category: {category}")
        context.user_data['category'] = category
        
        # İlk öncə qiyməti soruş
        await query.message.reply_text(
            "Slaydın qiymətini AZN ilə daxil edin:\n"
            "Qeyd: Satış baş tutduqda məbləğin 70%-i sizə ödəniləcək."
        )
        return UPLOAD_PRICE

async def handle_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text.strip())
        if price <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Zəhmət olmasa düzgün məbləğ daxil edin (məs: 5 və ya 5.5):")
        return UPLOAD_PRICE
    
    logger.info(f"User {update.message.from_user.id} entered price: {price}")
    context.user_data['price'] = price
    
    # Dil seçimi üçün klaviatura
    keyboard = [[InlineKeyboardButton(lang, callback_data=f"lang_{lang}")] for lang in LANGUAGES]
    
    await update.message.reply_text(
        "Təqdimatın dilini seçin:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return UPLOAD_LANGUAGE

async def handle_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    language = query.data.replace("lang_", "")
    logger.info(f"User {query.from_user.id} selected language: {language}")
    context.user_data['language'] = language
    
    await query.message.reply_text(
        "Təqdimatın səhifə sayını daxil edin:\n"
        "Rəqəm olaraq yazın (məs: 15)"
    )
    return UPLOAD_PAGES

async def handle_pages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        pages = int(update.message.text.strip())
        if pages <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Zəhmət olmasa düzgün səhifə sayı daxil edin (məs: 15):")
        return UPLOAD_PAGES
    
    logger.info(f"User {update.message.from_user.id} entered page count: {pages}")
    context.user_data['pages'] = pages
    
    await update.message.reply_text(
        "Kart nömrənizi daxil edin:\n"
        "Qeyd: Bu kart nömrəsinə satış baş tutduqda ödənişiniz göndəriləcək."
    )
    return UPLOAD_CARD
async def handle_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:  # Callback query varsa (geri düyməsinə basılıbsa)
        query = update.callback_query
        await query.answer()
        
        if query.data == "back_to_pages":
            # Səhifə sayına qayıt
            keyboard = [[InlineKeyboardButton("🔙 Geri", callback_data="back_to_language")]]
            await query.message.reply_text(
                "Təqdimatın səhifə sayını daxil edin:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return UPLOAD_PAGES
    
    # Normal mesaj gəlibsə (kart nömrəsi daxil edilibsə)
    elif update.message:
        user = update.message.from_user
        card = update.message.text.strip()
        
        if not card:
            keyboard = [[InlineKeyboardButton("🔙 Geri", callback_data="back_to_pages")]]
            await update.message.reply_text(
                "Kart nömrəsi boş ola bilməz. Zəhmət olmasa kart nömrəni daxil et:",
                # reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return UPLOAD_CARD
        
        logger.info(f"User {user.id} entered card number")
        context.user_data['card'] = card
        
        # Geri qayıtma düyməsi əlavə et
        keyboard = [[InlineKeyboardButton("🔙 Geri", callback_data="back_to_card")]]
        
        await update.message.reply_text(
            "Slayddan 1-2 şəkil göndər:\n"
            "Bu şəkillər axtarış zamanı nümunə kimi göstəriləcək.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return UPLOAD_IMAGE
    
    return ConversationHandler.END
async def handle_category_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    category = update.message.text.strip()
    
    if not category:
        await update.message.reply_text("Kateqoriya adı boş ola bilməz. Zəhmət olmasa kateqoriya adını daxil edin:")
        return UPLOAD_CATEGORY
    
    logger.info(f"User {user.id} entered custom category: {category}")
    context.user_data['category'] = category
    await update.message.reply_text("Kart nömrənizi daxil edin:\n"
        "Qeyd: Bu kart nömrəsinə satış baş tutduqda ödənişiniz göndəriləcək.")
    return UPLOAD_CARD



async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    
    if not update.message.photo:
        await update.message.reply_text("Zəhmət olmasa bir şəkil göndərin.")
        return UPLOAD_IMAGE
    
    try:
        photo = update.message.photo[-1]
        image_path = f"images/{uuid4()}.jpg"
        
        # Şəkili yüklə
        file = await photo.get_file()
        image_bytes = await file.download_as_bytearray()
        
        # Şəkili Pillow ilə aç və təmizlə
        image = Image.open(io.BytesIO(image_bytes))
        
        # Şəkili RGB formatına çevir
        image = image.convert("RGB")
        
        # Maksimum ölçüsünü təyin et (məsələn, 1280x1280)
        max_size = (1280, 1280)
        image.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # Şəklin ölçüsünü kiçilt (keyfiyyəti azaldaraq)
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=70, optimize=True)
        output.seek(0)
        
        # Şəkil ölçüsünü yoxla (Telegram şəkillər üçün 10MB limit var)
        image_size = len(output.getvalue()) / (1024 * 1024)  # MB olaraq
        logger.debug(f"Processed image size: {image_size:.2f} MB")
        
        if image_size > 10:
            logger.warning(f"Image size too large: {image_size:.2f} MB, attempting to reduce further")
            # Daha çox kiçilt
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=50, optimize=True)
            output.seek(0)
            image_size = len(output.getvalue()) / (1024 * 1024)
            logger.debug(f"Reduced image size: {image_size:.2f} MB")
            
            if image_size > 10:
                raise Exception(f"Image size still too large after compression: {image_size:.2f} MB")
        
        # Şəkili fayl olaraq saxla
        with open(image_path, 'wb') as f:
            f.write(output.getvalue())
        
        # Faylın düzgün saxlanıb saxlanmadığını yoxla
        if not os.path.exists(image_path):
            raise Exception("Failed to save image file")
        
        logger.info(f"User {user.id} uploaded a preview image: {image_path}, size: {image_size:.2f} MB")
        
        if 'images' not in context.user_data:
            context.user_data['images'] = []
        
        context.user_data['images'].append(image_path)
        
        keyboard = [
            [InlineKeyboardButton("✅ Tamamla", callback_data='finish_upload')],
            [InlineKeyboardButton("➕ Daha bir şəkil əlavə et", callback_data='add_more')]
        ]
        
        await update.message.reply_text(
            f"{len(context.user_data['images'])} şəkil yükləndi. Nə etmək istəyirsiniz?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return UPLOAD_IMAGE
    
    except Exception as e:
        logger.error(f"Error processing image for user {user.id}: {str(e)}")
        await update.message.reply_text(f"Şəkil yüklənərkən xəta baş verdi: {str(e)}. Zəhmət olmasa yenidən cəhd edin.")
        return UPLOAD_IMAGE
    
async def handle_image_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'add_more':
        await query.message.reply_text("Zəhmət olmasa daha bir şəkil göndər:")
        return UPLOAD_IMAGE
    
    elif query.data == 'finish_upload':
        if 'images' not in context.user_data or not context.user_data['images']:
            await query.message.reply_text("Ən azı bir şəkil yükləməlisiniz. Zəhmət olmasa şəkil göndərin:")
            return UPLOAD_IMAGE
        
        try:
            slide_id = str(uuid4())
            user = query.from_user
            
            # Get file extension and type
            file_path = context.user_data['slide_file']
            file_extension = os.path.splitext(file_path)[1].lower()
            
            # Get friendly file type name
            file_type_names = {
                '.pdf': 'PDF',
                '.ppt': 'PowerPoint',
                '.pptx': 'PowerPoint'
            }
            friendly_file_type = file_type_names.get(file_extension, 'Unknown')

            # Check if all required fields exist
            required_fields = ['name', 'category', 'price', 'card', 'slide_file', 'images']
            missing_fields = [field for field in required_fields if field not in context.user_data]
            
            if missing_fields:
                raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")
            
            # Create pending upload with all required fields
            pending_upload = {
                "slide_id": slide_id,
                "user_id": user.id,
                "user_name": user.full_name,
                "name": context.user_data['name'],
                "category": context.user_data['category'],
                "price": float(context.user_data['price']),  # Convert to float
                "language": context.user_data.get('language', 'Naməlum'),
                "pages": context.user_data.get('pages', 0),
                "card": context.user_data['card'],
                "file": context.user_data['slide_file'],
                "images": context.user_data['images'],
                "owner": user.id,
                "owner_name": user.full_name,
                "timestamp": str(query.message.date)
            }
            
            # Save pending upload
            save_pending_upload(pending_upload)
            
            # Adminə bildiriş göndər
            admin_text = (
                f"📤 Yeni slayd yükləndi!\n"
                f"İstifadəçi: {user.full_name} (ID: {user.id})\n"
                f"Slayd: {context.user_data['name']}\n"
                f"Kateqoriya: {context.user_data['category']}\n"
                f"Dil: {context.user_data.get('language', 'Naməlum')}\n"
                f"Səhifə sayı: {context.user_data.get('pages', 0)}\n"
                f"Qiymət: {context.user_data['price']} AZN\n"
                f"Format: {friendly_file_type} ({file_extension})\n"
                f"Kart: {context.user_data['card']}"
            )
            
            # Təsdiq və Rədd et düymələri
            keyboard = [
                [
                    InlineKeyboardButton("✅ Təsdiq Et", 
                        callback_data=f"approve_upload_{user.id}_{slide_id}"),
                    InlineKeyboardButton("❌ Rədd Et", 
                        callback_data=f"reject_upload_{user.id}_{slide_id}")
                ]
            ]

            # Send preview images and notification to admin
            for image_path in context.user_data['images']:
                await context.bot.send_photo(
                    chat_id=ADMIN_CHAT_ID,
                    photo=open(image_path, 'rb')
                )

            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=admin_text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Send the document to admin with correct file extension
            try:
                file_extension = context.user_data.get('file_extension', '.pdf')  # Use stored extension, default to .pdf
                filename = f"{pending_upload['name']}{file_extension}"
                with open(pending_upload['file'], 'rb') as f:
                    await context.bot.send_document(
                        chat_id=ADMIN_CHAT_ID,
                        document=f,
                        filename=filename,
                        reply_markup=reply_markup
                    )
            except Exception as e:
                logger.error(f"Failed to send document to admin: {e}")
                await context.bot.send_message(
                    chat_id=ADMIN_CHAT_ID,
                    text=admin_text + f"\n\n⚠️ Document faylı göndərilə bilmədi: {str(e)}",
                    reply_markup=reply_markup
                )
            
            # Önizləmə şəkillərini baytlar olaraq göndər
            for i, img_path in enumerate(pending_upload['images'], start=1):
                try:
                    if not os.path.exists(img_path):
                        logger.error(f"Preview image not found: {img_path}")
                        await context.bot.send_message(
                            chat_id=ADMIN_CHAT_ID,
                            text=f"⚠️ Önizləmə şəkli {i} tapılmadı: {img_path}"
                        )
                        continue
                    
                    # Şəkili baytlar olaraq oxu
                    with open(img_path, 'rb') as f:
                        image_bytes = f.read()
                        logger.debug(f"Preview image {i} loaded as bytes, size: {len(image_bytes) / 1024:.2f} KB")
                    
                    # Şəkili baytlar olaraq göndər
                    await context.bot.send_photo(
                        chat_id=ADMIN_CHAT_ID,
                        photo=image_bytes,
                        caption=f"Önizləmə şəkli {i} - Slayd: {pending_upload['name']}"
                    )
                    logger.info(f"Successfully sent preview image {i} as bytes")
                
                except Exception as e:
                    logger.error(f"Failed to send preview image {i} as bytes: {e}")
                    await context.bot.send_message(
                        chat_id=ADMIN_CHAT_ID,
                        text=f"⚠️ Önizləmə şəkli {i} yüklənə bilmədi."
                    )
            
            # İstifadəçiyə təsdiq gözləmə mesajı
            await query.message.reply_text(
                "✅ Slaydınız qeydə alındı!\n\n"
                "Admin təsdiq etdikdən sonra slayd paylaşılanlar siyahısına əlavə olunacaq.\n"
                "Təşəkkürlər!"
            )
            
            logger.info(f"User {user.id} ({user.full_name}) submitted slide for approval: {pending_upload['name']}")
            
            context.user_data.clear()
            return ConversationHandler.END
            
        except Exception as e:
            logger.error(f"Error processing upload: {e}")
            await query.message.reply_text("Slayd qeydə alınarkən xəta baş verdi. Zəhmət olmasa yenidən cəhd edin.")
            return ConversationHandler.END
        
async def reject_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if str(query.message.chat_id) != str(ADMIN_CHAT_ID):
        await query.message.reply_text("Bu əmr yalnız admin üçün əlçatandır.")
        return
    
    try:
        parts = query.data.split('_')
        user_id = int(parts[2])
        slide_id = parts[3]
        
        # Müvəqqəti yükləmələrdən məlumatı tap
        pending_uploads = load_pending_uploads()
        upload = next((u for u in pending_uploads if u['user_id'] == user_id and u['slide_id'] == slide_id), None)
        
        if not upload:
            logger.error(f"Pending upload not found for user ID: {user_id}, slide ID: {slide_id}")
            await query.message.reply_text(f"Yükləmə məlumatları tapılmadı (User ID: {user_id}, Slide ID: {slide_id}).")
            return
        
        # Müvəqqəti yükləmələrdən sil
        remove_pending_upload(user_id, slide_id)
        
        # İstifadəçiyə rədd mesajı göndər
        await context.bot.send_message(
            chat_id=user_id,
            text=f"❌ Sizin slaydınız ('{upload['name']}') admin tərəfindən rədd edildi.\n"
                 "Zəhmət olmasa yenidən cəhd edin və ya adminlə əlaqə saxlayın (@UniSlayd)."
        )
        
        # Adminə rədd mesajı
        await query.message.reply_text(f"✅ Slayd (ID: {slide_id}) rədd edildi.")
        
        logger.info(f"Admin rejected upload for user ID: {user_id}, slide ID: {slide_id}")
        
    except Exception as e:
        logger.error(f"Error rejecting upload: {e}")
        await query.message.reply_text(f"Xəta: {str(e)}")
# -- Search Flow --
async def handle_search_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'search_by_name':
        await query.message.reply_text(
            "Axtarmaq istədiyiniz slaydın adını daxil edin:",
            reply_markup=ReplyKeyboardRemove()
        )
        return SEARCH_TYPE
        
    elif query.data == 'search_by_category':
        # Kateqoriyaları 3 sütun x 5 sətir formatında göstər
        keyboard = []
        for i in range(0, len(CATEGORIES), 3):
            row = [
                InlineKeyboardButton(CATEGORIES[j], callback_data=f"search_category_{CATEGORIES[j]}")
                for j in range(i, min(i + 3, len(CATEGORIES)))
            ]
            keyboard.append(row)
        
        await query.message.reply_text(
            "Kateqoriyanı seçin:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SEARCH_CATEGORY
        
    elif query.data == 'search_by_language':
        keyboard = [[InlineKeyboardButton(lang, callback_data=f"search_lang_{lang}")] for lang in LANGUAGES]
        keyboard.append([InlineKeyboardButton("🔙 Əsas Menyu", callback_data="main_menu")])
        
        await query.message.reply_text(
            "Hansı dildə təqdimat axtarırsınız?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SEARCH_LANGUAGE

async def handle_search_by_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    language = query.data.replace("search_lang_", "")
    
    logger.info(f"User {query.from_user.id} searched by language: {language}")
    
    slides = load_slides()
    results = [slide for slide in slides if slide.get('language', '').lower() == language.lower()]
    
    context.user_data['results'] = results
    
    if not results:
        await query.message.reply_text(
            f"'{language}' dilində heç bir təqdimat tapılmadı.\n"
            "Başqa dildə axtarış üçün /start yazaraq əsas menyuya qayıdın."
        )
        return ConversationHandler.END
    
    keyboard = []
    for i, slide in enumerate(results):
        button_text = f"{slide['name']} [{slide.get('language', 'Naməlum')}]"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"slide_{i}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Əsas Menyu", callback_data="main_menu")])
    
    await query.message.reply_text(
        f"'{language}' dilində {len(results)} təqdimat tapıldı:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_SLIDE

async def handle_search_by_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        logger.error("No message found in update")
        return SEARCH_TYPE
    
    user = update.message.from_user
    name = update.message.text.lower().strip()
    
    if not name:
        await update.message.reply_text("Slayd adı boş ola bilməz. Zəhmət olmasa slaydın adını daxil edin:")
        return SEARCH_TYPE
    
    logger.info(f"User {user.id} ({user.full_name}) searched by name: {name}")
    
    slides = load_slides()
    results = [
        slide for slide in slides
        if name in slide['name'].lower()
    ]
    
    context.user_data['results'] = results
    
    if not results:
        await update.message.reply_text(
            f"'{name}' adına uyğun heç bir nəticə tapılmadı.\n"
            "Yeni axtarış üçün başqa ad daxil edin və ya /start yazaraq əsas menyuya qayıdın."
        )
        return SEARCH_TYPE
    
    keyboard = []
    for i, slide in enumerate(results):
        # "category" sahəsinin mövcudluğunu yoxla və varsayılan dəyər təyin et
        category = slide.get('category', 'Naməlum')
        button_text = f"{slide['name']} [Kateqoriya: {category}]"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"slide_{i}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Əsas Menyu", callback_data="main_menu")])
    
    await update.message.reply_text(
        f"'{name}' adına uyğun {len(results)} nəticə tapıldı:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_SLIDE

async def handle_search_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    category = query.data.replace("search_category_", "")
    
    if category == "Digər":
        await query.message.reply_text("Zəhmət olmasa kateqoriya adını daxil edin:")
        return SEARCH_OTHER_CATEGORY
    
    logger.info(f"User {query.from_user.id} searched by category: {category}")
    
    slides = load_slides()
    results = []
    for slide in slides:
        # 'category' sahəsinin mövcudluğunu yoxla, yoxdursa boş string qaytar
        slide_category = slide.get('category', '').lower()
        if slide_category == category.lower():
            results.append(slide)
    
    context.user_data['results'] = results
    
    if not results:
        await query.message.reply_text(
            f"'{category}' kateqoriyasında heç bir nəticə tapılmadı.\n"
            "Başqa kateqoriya seçmək üçün /start yazaraq əsas menyuya qayıdın."
        )
        return SEARCH_TYPE
    
    keyboard = []
    for i, slide in enumerate(results):
        button_text = f"{slide['name']} [Kateqoriya: {slide.get('category', 'Naməlum')}]"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"slide_{i}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Əsas Menyu", callback_data="main_menu")])
    
    await query.message.reply_text(
        f"'{category}' kateqoriyasında {len(results)} nəticə tapıldı:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_SLIDE

async def handle_search_other_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        logger.error("No message found in update")
        return SEARCH_OTHER_CATEGORY
    
    user = update.message.from_user
    category = update.message.text.lower().strip()
    
    if not category:
        await update.message.reply_text("Kateqoriya adı boş ola bilməz. Zəhmət olmasa kateqoriya adını daxil edin:")
        return SEARCH_OTHER_CATEGORY
    
    logger.info(f"User {user.id} ({user.full_name}) searched by custom category: {category}")
    
    slides = load_slides()
    results = []
    for slide in slides:
        # 'category' sahəsinin mövcudluğunu yoxla və varsayılan dəyər təyin et
        slide_category = slide.get('category', '').lower()
        if slide_category == category:
            results.append(slide)
    
    context.user_data['results'] = results
    
    if not results:
        await update.message.reply_text(
            f"'{category}' kateqoriyasında heç bir nəticə tapılmadı.\n"
            "Başqa kateqoriya üçün /start yazaraq əsas menyuya qayıdın."
        )
        return SEARCH_TYPE
    
    keyboard = []
    for i, slide in enumerate(results):
        button_text = f"{slide['name']} [Kateqoriya: {slide.get('category', 'Naməlum')}]"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"slide_{i}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Əsas Menyu", callback_data="main_menu")])
    
    await update.message.reply_text(
        f"'{category}' kateqoriyasında {len(results)} nəticə tapıldı:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_SLIDE

async def handle_search_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    category = query.data.replace("search_category_", "")
    
    if category == "Digər":
        await query.message.reply_text("Zəhmət olmasa kateqoriya adını daxil edin:")
        return SEARCH_OTHER_CATEGORY
    
    logger.info(f"User {query.from_user.id} searched by category: {category}")
    
    slides = load_slides()
    results = []
    for slide in slides:
        # 'category' sahəsinin mövcudluğunu yoxla, yoxdursa boş string qaytar
        slide_category = slide.get('category', '').lower()
        if slide_category == category.lower():
            results.append(slide)
    
    context.user_data['results'] = results
    
    if not results:
        await query.message.reply_text(
            f"'{category}' kateqoriyasında heç bir nəticə tapılmadı.\n"
            "Başqa kateqoriya seçmək üçün /start yazaraq əsas menyuya qayıdın."
        )
        return SEARCH_TYPE
    
    keyboard = []
    for i, slide in enumerate(results):
        button_text = f"{slide['name']} [Kateqoriya: {slide.get('category', 'Naməlum')}]"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"slide_{i}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Əsas Menyu", callback_data="main_menu")])
    
    await query.message.reply_text(
        f"'{category}' kateqoriyasında {len(results)} nəticə tapıldı:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_SLIDE
async def back_to_results(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if 'results' not in context.user_data or not context.user_data['results']:
        keyboard = [
            [InlineKeyboardButton("📛 Ad ilə axtar", callback_data='search_by_name')],
            [InlineKeyboardButton("📚 Kateqoriya ilə axtar", callback_data='search_by_category')]
        ]
        await query.message.reply_text(
            "Axtarış üsulunu seçin:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SEARCH_TYPE
    
    keyboard = []
    for i, slide in enumerate(context.user_data['results']):
        button_text = f"{slide['name']} [Kateqoriya: {slide['category']}]"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"slide_{i}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Əsas Menyu", callback_data="main_menu")])
    
    await query.message.reply_text(
        f"Axtarış nəticələri:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_SLIDE

async def request_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    slide = context.user_data.get('selected_slide')
    if not slide:
        await query.message.reply_text("Xəta baş verdi. Zəhmət olmasa yenidən cəhd edin.")
        return ConversationHandler.END
    
    payment_text = (
        f"💰 Ödəniş məlumatları:\n\n"
        f"💳 *Kart nömrəsi:* `4098584494745886`\n\n"
        f"Zəhmət olmasa bu kart nömrəsinə {slide['price']} AZN məbləğində ödəniş edin və "
        f"ödəniş qəbzinin şəklini göndərin. Ödəniş təsdiqlənəndən sonra "
        f"slayd sizə göndəriləcək."
    )
    
    await query.message.reply_text(
        payment_text,
        parse_mode="Markdown"
    )
    
    await query.message.reply_text(
        "Zəhmət olmasa ödəniş etdiyiniz qəbzin şəklini göndərin:"
    )
    return CONFIRM_PAYMENT

async def view_selected_slide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "main_menu":
        keyboard = [
            [InlineKeyboardButton("📤 Slayd yüklə", callback_data='upload')],
            [InlineKeyboardButton("🔍 Slayd axtar", callback_data='search')]
        ]
        await query.message.reply_text(
            "Əsas menyu:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ConversationHandler.END
    
    try:
        index = int(query.data.split('_')[1])
        slide = context.user_data['results'][index]
        context.user_data['selected_slide'] = slide
        
        logger.info(f"User {query.from_user.id} ({query.from_user.full_name}) selected slide: {slide['name']}")
        
        # Get values with defaults if fields don't exist
        category = slide.get('category', 'Naməlum')
        price = slide.get('price', 0)  # Default price is 0 if not set
        
        info_text = (
            f"📝 *{slide['name']}*\n\n"
            f"📌 *Kateqoriya:* {category}\n"
            f"🌐 *Dil:* {slide.get('language', 'Qeyd edilməyib')}\n"
            f"📄 *Səhifə sayı:* {slide.get('pages', 'Qeyd edilməyib')}\n"
            f"💰 *Qiymət:* {price} AZN\n"
            f"💳 *Kart nömrəsi:* `4098584494745886`\n"
        )
        
        # Önizləmə şəkillərini göndər
        if 'images' in slide and slide['images']:
            for i, img_path in enumerate(slide['images'], start=1):
                try:
                    if not os.path.exists(img_path):
                        logger.error(f"Image file not found: {img_path}")
                        continue
                        
                    with open(img_path, 'rb') as f:
                        await query.message.reply_photo(
                            photo=f,
                            parse_mode="Markdown"
                        )
                except Exception as e:
                    logger.error(f"Error sending preview image {i}: {e}")
                    continue
        
        await query.message.reply_text(
            info_text,
            parse_mode="Markdown"
        )
        
        keyboard = [
            [InlineKeyboardButton("✅ Təqdimatı al", callback_data="buy")],
            [InlineKeyboardButton("🔙 Geri", callback_data="back_to_results")]
        ]
        
        await query.message.reply_text(
            "Nə etmək istəyirsiniz?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return CONFIRM_PAYMENT
        
    except Exception as e:
        logger.error(f"Error in view_selected_slide: {str(e)}")
        await query.message.reply_text(
            "Xəta baş verdi. Zəhmət olmasa yenidən cəhd edin."
        )
        return ConversationHandler.END


async def reject_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if str(query.message.chat_id) != str(ADMIN_CHAT_ID):
        await query.message.reply_text("Bu əmr yalnız admin üçün əlçatandır.")
        return
    
    try:
        user_id = int(query.data.split('_')[-1])
        
        # payments.json faylını yoxla
        if not os.path.exists('payments.json'):
            logger.error("Payments file not found")
            await query.message.reply_text("Ödəniş məlumatları faylı tapılmadı.")
            return
        
        with open('payments.json', 'r', encoding='utf-8') as f:
            payments = json.load(f)
        
        payment = next((p for p in payments if p['user_id'] == user_id), None)
        if not payment:
            logger.error(f"Payment data not found for user ID: {user_id}")
            await query.message.reply_text(f"Ödəniş məlumatları tapılmadı (ID: {user_id}).")
            return
        
        # Ödənişi payments.json-dan sil
        payments = [p for p in payments if p['user_id'] != user_id]
        with open('payments.json', 'w', encoding='utf-8') as f:
            json.dump(payments, f, indent=2, ensure_ascii=False)
        
        # İstifadəçiyə rədd mesajı göndər
        await context.bot.send_message(
            chat_id=user_id,
            text=f"❌ Ödənişiniz admin tərəfindən rədd edildi (Slayd: {payment['slide_name']}).\n"
                 "Zəhmət olmasa yenidən cəhd edin və ya adminlə əlaqə saxlayın (@UniSlayd)."
        )
        
        # Adminə rədd mesajı
        await query.message.reply_text(f"✅ Ödəniş (ID: {user_id}) rədd edildi.")
        
        logger.info(f"Admin rejected payment for user ID: {user_id}")
        
    except Exception as e:
        logger.error(f"Error rejecting payment: {e}")
        await query.message.reply_text(f"Xəta: {str(e)}")

async def confirm_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    
    if not update.message.photo:
        await update.message.reply_text(
            "Zəhmət olmasa ödəniş qəbzinin şəklini göndərin."
        )
        return ConversationHandler.END
    
    slide = context.user_data.get('selected_slide')
    if not slide:
        logger.error("No selected slide found in user_data")
        await update.message.reply_text("Xəta baş verdi. Zəhmət olmasa yenidən cəhd edin.")
        return ConversationHandler.END
    
    try:
        payment_image = update.message.photo[-1]
        image_path = f"payments/{uuid4()}.jpg"
        
        # Şəkili yüklə və optimallaşdır
        file = await payment_image.get_file()
        image_bytes = await file.download_as_bytearray()
        
        # Şəkili Pillow ilə aç və optimallaşdır
        image = Image.open(io.BytesIO(image_bytes))
        image = image.convert("RGB")  # RGB formatına çevir
        
        # Maksimum ölçüsünü təyin et (məsələn, 640x640)
        max_size = (640, 640)
        image.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # Bütün metadata-nı təmizlə
        image_info = image.info.copy()
        image_info.pop('exif', None)
        image_info.pop('icc_profile', None)
        
        # Şəkili JPEG olaraq saxla
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=70, optimize=True, **image_info)
        output.seek(0)
        
        # Şəkili fayl olaraq saxla
        with open(image_path, 'wb') as f:
            f.write(output.getvalue())
        
        # Faylın düzgün saxlanıb-saxlanmadığını yoxla
        if not os.path.exists(image_path):
            raise Exception(f"Failed to save image file: {image_path}")
        
        image_size = os.path.getsize(image_path) / 1024  # KB olaraq
        logger.info(f"User {user.id} ({user.full_name}) submitted payment for slide: {slide['name']}, image size: {image_size:.2f} KB")
        logger.debug(f"Slide file path: {slide['file']}, payment image path: {image_path}")
        
        # Ödəniş məlumatlarını faylda saxla
        payment_data = {
            'user_id': user.id,
            'slide_file': slide['file'],
            'slide_name': slide['name'],
            'timestamp': str(update.message.date),
            'payment_image': image_path
        }
        if not os.path.exists('payments.json'):
            with open('payments.json', 'w', encoding='utf-8') as f:
                json.dump([], f, indent=2, ensure_ascii=False)
        
        with open('payments.json', 'r', encoding='utf-8') as f:
            payments = json.load(f)
        payments.append(payment_data)
        with open('payments.json', 'w', encoding='utf-8') as f:
            json.dump(payments, f, indent=2, ensure_ascii=False)
        
        admin_text = (
            f"💸 Yeni ödəniş!\n"
            f"İstifadəçi: {user.full_name} (ID: {user.id})\n"
            f"Slayd: {slide['name']}\n"
            f"Satıcı: {slide.get('owner_name', 'Naməlum')} (ID: {slide.get('owner', 'Naməlum')})\n"
            f"Kart: {slide['card']}\n"
        )
        
        # Təsdiq və Rədd et düymələri
        keyboard = [
            [
                InlineKeyboardButton("✅ Təsdiq Et", callback_data=f"approve_payment_{user.id}"),
                InlineKeyboardButton("❌ Rədd Et", callback_data=f"reject_payment_{user.id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Şəkili baytlar olaraq göndər
        try:
            with open(image_path, 'rb') as f:
                image_bytes = f.read()
            await context.bot.send_photo(
                chat_id=ADMIN_CHAT_ID,
                photo=image_bytes,
                caption=admin_text,
                reply_markup=reply_markup
            )
            logger.info("Successfully sent payment image as bytes with buttons")
        except Exception as e:
            logger.error(f"Failed to send payment image as bytes: {e}")
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=admin_text,
                reply_markup=reply_markup
            )
        
        await update.message.reply_text(
            "✅ Ödənişiniz qeydə alındı!\n\n"
            "Admin ödənişi təsdiq etdikdən sonra təqdimat faylı sizə göndəriləcək.\n"
            "Təşəkkürlər!"
        )
        
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error processing payment: {e}")
        await update.message.reply_text(
            "Ödəniş qəbzi yüklənərkən xəta baş verdi. Zəhmət olmasa yenidən cəhd edin."
        )
        return ConversationHandler.END
    
async def approve_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if str(query.message.chat_id) != str(ADMIN_CHAT_ID):
        await query.message.reply_text("Bu əmr yalnız admin üçün əlçatandır.")
        return

    try:
        user_id = int(query.data.split('_')[2])
        
        # Load payments
        with open('payments.json', 'r', encoding='utf-8') as f:
            payments = json.load(f)
        
        # Find payment
        payment = next((p for p in payments if p['user_id'] == user_id), None)
        if not payment:
            raise ValueError(f"Payment not found for user ID: {user_id}")

        # Load slides
        slides = load_slides()
        
        # Find slide
        slide = next((s for s in slides if s['file'] == payment['slide_file']), None)
        if not slide:
            raise ValueError(f"Slide not found: {payment['slide_name']}")

        # Update sales count
        if 'sales' in slide:
            slide['sales'] += 1
        else:
            slide['sales'] = 1

        # Save updated slides
        with open(DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(slides, f, indent=2, ensure_ascii=False)

        # Calculate seller amount (85% of price)
        seller_amount = float(slide['price']) * 0.85

        # Send payment details to admin
        await query.message.reply_text(
            f"💰 *Ödəniş edilməlidir:*\n\n"
            f"👤 İstifadəçi ID: `{slide['owner']}`\n"
            f"💳 Kart: `{slide['card']}`\n"
            f"💵 Məbləğ: *{seller_amount:.2f} AZN*\n"
            f"_(Satış məbləği: {slide['price']} AZN)_",
            parse_mode="Markdown"
        )

        # Send slide to buyer
        if os.path.exists(slide['file']):
            file_extension = os.path.splitext(slide['file'])[1].lower()
            with open(slide['file'], 'rb') as f:
                await context.bot.send_document(
                    chat_id=user_id,
                    document=f,
                    filename=f"{slide['name']}{file_extension}",
                    caption=f"Təqdimat: {slide['name']}"
                )

            # Notify buyer
            await context.bot.send_message(
                chat_id=user_id,
                text="✅ Ödənişiniz təsdiqləndi! Slayd faylı yuxarıda göndərildi."
            )

            # Remove payment record
            payments = [p for p in payments if p['user_id'] != user_id]
            with open('payments.json', 'w', encoding='utf-8') as f:
                json.dump(payments, f, indent=2, ensure_ascii=False)

            # Confirm to admin
            await query.message.reply_text(f"✅ İstifadəçiyə (ID: {user_id}) slayd göndərildi.")
        else:
            raise FileNotFoundError(f"Slide file not found: {slide['file']}")

    except Exception as e:
        logger.error(f"Error approving payment: {e}")
        await query.message.reply_text(f"Xəta: {str(e)}")

# Müvəqqəti yükləmələri saxlamaq üçün fayl
PENDING_UPLOADS_FILE = "pending_uploads.json"

def load_pending_uploads():
    if os.path.exists(PENDING_UPLOADS_FILE):
        try:
            with open(PENDING_UPLOADS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.error(f"Error decoding {PENDING_UPLOADS_FILE}. Creating empty database.")
            return []
    return []

def save_pending_upload(upload):
    uploads = load_pending_uploads()
    uploads.append(upload)
    with open(PENDING_UPLOADS_FILE, 'w', encoding='utf-8') as f:
        json.dump(uploads, f, indent=2, ensure_ascii=False)

def remove_pending_upload(user_id, slide_id):
    uploads = load_pending_uploads()
    uploads = [upload for upload in uploads if not (upload['user_id'] == user_id and upload['slide_id'] == slide_id)]
    with open(PENDING_UPLOADS_FILE, 'w', encoding='utf-8') as f:
        json.dump(uploads, f, indent=2, ensure_ascii=False)


async def approve_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if str(query.message.chat_id) != str(ADMIN_CHAT_ID):
        await query.message.reply_text("Bu əmr yalnız admin üçün əlçatandır.")
        return
    
    try:
        parts = query.data.split('_')
        user_id = int(parts[2])
        slide_id = parts[3]
        
        # Müvəqqəti yükləmələrdən məlumatı tap
        pending_uploads = load_pending_uploads()
        upload = next((u for u in pending_uploads if u['user_id'] == user_id and u['slide_id'] == slide_id), None)
        
        if not upload:
            logger.error(f"Pending upload not found for user ID: {user_id}, slide ID: {slide_id}")
            await query.message.reply_text(f"Yükləmə məlumatları tapılmadı (User ID: {user_id}, Slide ID: {slide_id}).")
            return
        file_extension = os.path.splitext(upload['file'])[1].lower()
        # Ensure all required fields exist with default values
        slide = {
            "id": upload['slide_id'],
            "name": upload['name'],
            "category": upload['category'],
            "language": upload.get('language', 'Naməlum'),
            "pages": upload.get('pages', 0),
            "price": upload['price'],
            "card": upload['card'],
            "file": upload['file'],
            "file_type": upload.get('file_type', 'application/pdf'), 
            "file_type": file_extension.replace('.', ''),
            "images": upload['images'],
            "owner": upload['owner'],
            "owner_name": upload['owner_name'],
            "timestamp": upload['timestamp']
        }
        
        save_slide(slide)
        remove_pending_upload(user_id, slide_id)
        
        # User confirmation message
        await context.bot.send_message(
            chat_id=user_id,
            text=f"✅ Sizin slaydınız ('{upload['name']}') admin tərəfindən təsdiqləndi və paylaşıldı!\n"
                 "İndi digər istifadəçilər axtarış zamanı slaydınızı tapa bilərlər."
        )
        
        # Admin confirmation message
        await query.message.reply_text(f"✅ Slayd (ID: {slide_id}) təsdiqləndi və paylaşıldı.")
        
        logger.info(f"Admin approved upload for user ID: {user_id}, slide ID: {slide_id}")
        
    except Exception as e:
        logger.error(f"Error approving upload: {e}")
        await query.message.reply_text(f"Xəta: {str(e)}")
# -- Help Command --
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🌟 *UniSlayd Bot Kömək*\n\n"
        "*Əsas əmrlər:*\n"
        "• /start - Botu yenidən başladır\n"
        "• /help - Bu kömək mesajını göstərir\n"
        "• /cancel - Cari əməliyyatı ləğv edir\n\n"
        
        "*Slayd yükləmək üçün:*\n"
        "1. 'Slayd yüklə' düyməsini seçin\n"
        "2. 30MB-dan kiçik slayd faylı göndərin\n"
        "3. Slaydın adını daxil edin\n"
        "4. Kateqoriya seçin (və ya 'Digər' seçərək öz kateqoriyanızı daxil edin)\n"
        "5. Ödəniş almaq üçün kartınızın nömrəsini daxil edin\n"
        "6. Slayddan 1-2 önizləmə şəkli göndərin\n\n"
        
        "*Slayd axtarmaq üçün:*\n"
        "1. 'Slayd axtar' düyməsini seçin\n"
        "2. Ad ilə axtarış və ya kateqoriya ilə axtarış seçin\n"
        "3. Siyahıdan istədiyiniz slaydı seçin\n"
        "4. 'Təqdimatı al' düyməsini basın\n"
        "5. Göstərilən karta ödəniş edin və qəbzin şəklini göndərin\n"
        "6. Admin ödənişi təsdiq etdikdən sonra slayd sizə göndəriləcək\n\n"
        
        "Hər hansı bir probleminiz varsa @UniSlayd ilə əlaqə saxlayın."
    )
    
    await update.message.reply_text(
        help_text,
        parse_mode="Markdown"
    )

async def handle_edit_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "back_to_slide_action":
        slide = context.user_data.get('selected_slide')
        if not slide:
            await query.message.reply_text("Xəta: Seçilmiş slayd tapılmadı.")
            return ConversationHandler.END

        keyboard = [
            [InlineKeyboardButton("✏️ Düzəliş et", callback_data="edit_slide")],
            [InlineKeyboardButton("🗑️ Sil", callback_data="delete_slide")],
            [InlineKeyboardButton("🔙 Geri", callback_data="back_to_slides")]
        ]

        await query.message.reply_text(
            "Nə etmək istəyirsiniz?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECT_SLIDE_ACTION

    field_map = {
        "edit_name": ("Ad", "Yeni adı daxil edin:"),
        "edit_price": ("Qiymət", "Yeni qiyməti AZN ilə daxil edin (məs: 5.5):"),
        "edit_pages": ("Səhifə sayı", "Yeni səhifə sayını daxil edin (məs: 15):"),
        "edit_card": ("Kart", "Yeni kart nömrəsini daxil edin:")
    }

    if query.data not in field_map:
        await query.message.reply_text("Xəta: Yanlış sahə seçildi.")
        return EDIT_FIELD

    field, prompt = field_map[query.data]
    context.user_data['edit_field'] = field.lower()

    if field == "Kateqoriya":
        keyboard = []
        for i in range(0, len(CATEGORIES), 3):
            row = [
                InlineKeyboardButton(CATEGORIES[j], callback_data=f"edit_category_{CATEGORIES[j]}")
                for j in range(i, min(i + 3, len(CATEGORIES)))
            ]
            keyboard.append(row)
        await query.message.reply_text(prompt, reply_markup=InlineKeyboardMarkup(keyboard))
    elif field == "Dil":
        keyboard = [[InlineKeyboardButton(lang, callback_data=f"edit_language_{lang}")] for lang in LANGUAGES]
        await query.message.reply_text(prompt, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await query.message.reply_text(prompt, reply_markup=ReplyKeyboardRemove())

    return EDIT_VALUE

async def handle_slide_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "back_to_slides":
        user_slides = context.user_data.get('user_slides', [])
        if not user_slides:
            await query.message.reply_text("Sizin təqdimatınız yoxdur.")
            return ConversationHandler.END

        keyboard = []
        for i, slide in enumerate(user_slides):
            button_text = f"{slide['name']} [Kateqoriya: {slide.get('category', 'Naməlum')}]"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"myslide_{i}")])

        keyboard.append([InlineKeyboardButton("🔙 Əsas Menyu", callback_data="main_menu")])

        await query.message.reply_text(
            f"Sizin {len(user_slides)} təqdimatınız tapıldı:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return MY_SLIDES

    elif query.data == "delete_slide":
        slide = context.user_data.get('selected_slide')
        if not slide:
            await query.message.reply_text("Xəta: Seçilmiş slayd tapılmadı.")
            return ConversationHandler.END

        try:
            # Load all slides
            slides = load_slides()
            
            # Find and remove the slide
            slides = [s for s in slides if s['id'] != slide['id']]
            
            # Save updated slides list
            with open(DB_FILE, 'w', encoding='utf-8') as f:
                json.dump(slides, f, indent=2, ensure_ascii=False)

            # Delete associated files
            try:
                if os.path.exists(slide['file']):
                    os.remove(slide['file'])
                for img_path in slide.get('images', []):
                    if os.path.exists(img_path):
                        os.remove(img_path)
            except Exception as e:
                logger.error(f"Error deleting files for slide {slide['id']}: {e}")

            await query.message.reply_text(f"✅ Slayd '{slide['name']}' silindi.")
            
            # Update user's slides list
            user_slides = [s for s in slides if s['owner'] == query.from_user.id]
            context.user_data['user_slides'] = user_slides
            
            if user_slides:
                keyboard = []
                for i, s in enumerate(user_slides):
                    button_text = f"{s['name']} [Kateqoriya: {s.get('category', 'Naməlum')}]"
                    keyboard.append([InlineKeyboardButton(button_text, callback_data=f"myslide_{i}")])
                
                keyboard.append([InlineKeyboardButton("🔙 Əsas Menyu", callback_data="main_menu")])
                
                await query.message.reply_text(
                    f"Sizin {len(user_slides)} təqdimatınız qaldı:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return MY_SLIDES
            else:
                await query.message.reply_text("Sizin artıq heç bir təqdimatınız yoxdur.")
                return ConversationHandler.END
                
        except Exception as e:
            logger.error(f"Error deleting slide: {e}")
            await query.message.reply_text("Slaydı silməyə çalışarkən xəta baş verdi.")
            return ConversationHandler.END
        
    elif query.data == "edit_slide":
        keyboard = [
            [InlineKeyboardButton("Ad", callback_data="edit_name")],
            [InlineKeyboardButton("Qiymət", callback_data="edit_price")],
            [InlineKeyboardButton("Səhifə sayı", callback_data="edit_pages")],
            [InlineKeyboardButton("Kart", callback_data="edit_card")],
            [InlineKeyboardButton("🔙 Geri", callback_data="back_to_slide_action")]
        ]

        await query.message.reply_text(
            "Hansı sahəni düzəltmək istəyirsiniz?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return EDIT_FIELD
    
# Handler for editing category
async def handle_edit_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle language update with improved error handling and UI feedback"""
    query = update.callback_query
    await query.answer()

    try:
        language = query.data.replace("edit_language_", "")
        slide = context.user_data.get('selected_slide')
        if not slide:
            await query.edit_message_text("Xəta: Seçilmiş slayd tapılmadı.")
            return ConversationHandler.END

        # First, update the UI to show processing
        await query.edit_message_text(f"Dil '{language}' olaraq yenilənir... Xahiş edirik gözləyin.")
        
        # Load slides directly from file to ensure we have latest data
        slides = load_slides()
        
        # Find and update the specific slide
        updated = False
        for s in slides:
            if s['id'] == slide['id']:
                s['language'] = language
                # Save the updated slide back to context
                context.user_data['selected_slide'] = s
                updated = True
                break
        
        if not updated:
            await query.edit_message_text("Xəta: Slayd verilənlər bazasında tapılmadı.")
            return ConversationHandler.END

        # Save all slides with explicit error handling
        try:
            with open(DB_FILE, 'w', encoding='utf-8') as f:
                json.dump(slides, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving slides to file: {e}")
            await query.edit_message_text(f"Verilənlər bazasını yadda saxlayarkən xəta: {str(e)}")
            return ConversationHandler.END

        # Update user's slides list in context
        user_slides = context.user_data.get('user_slides', [])
        for i, s in enumerate(user_slides):
            if s['id'] == slide['id']:
                user_slides[i]['language'] = language
                break
        context.user_data['user_slides'] = user_slides

        # Update UI with success message and options
        keyboard = [
            [InlineKeyboardButton("🔄 Redaktə etməyə davam edin", callback_data=f"edit_slide_{slide['id']}")],
            [InlineKeyboardButton("🔙 Slaydlara qayıt", callback_data="my_slides")]
        ]
        
        await query.edit_message_text(
            f"✅ Dil '{language}' olaraq uğurla yeniləndi.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return MY_SLIDES

    except Exception as e:
        logger.error(f"Error in handle_edit_language: {e}")
        # Provide user with error and recovery option
        keyboard = [[InlineKeyboardButton("🔙 Əsas Menyu", callback_data="main_menu")]]
        await query.edit_message_text(
            f"Xəta baş verdi. Zəhmət olmasa yenidən cəhd edin.\nXəta detalları: {str(e)}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ConversationHandler.END

async def handle_edit_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle category update with improved error handling and UI feedback"""
    query = update.callback_query
    await query.answer()

    try:
        category = query.data.replace("edit_category_", "")
        slide = context.user_data.get('selected_slide')
        if not slide:
            await query.edit_message_text("Xəta: Seçilmiş slayd tapılmadı.")
            return ConversationHandler.END

        # First, update the UI to show processing
        await query.edit_message_text(f"Kateqoriya '{category}' olaraq yenilənir... Xahiş edirik gözləyin.")
        
        # Load slides directly from file to ensure we have latest data
        slides = load_slides()
        
        # Find and update the specific slide
        updated = False
        for i, s in enumerate(slides):
            if s['id'] == slide['id']:
                slides[i]['category'] = category
                context.user_data['selected_slide'] = slides[i]  # Update in context
                updated = True
                logger.debug(f"Updated slide ID: {slide['id']} with new category: {category}")
                break
        
        if not updated:
            await query.edit_message_text("Xəta: Slayd verilənlər bazasında tapılmadı.")
            return ConversationHandler.END

        # Save updated slides with explicit error handling
        try:
            save_slides(slides)
        except Exception as e:
            logger.error(f"Error saving slides to file: {e}")
            await query.edit_message_text(f"Verilənlər bazasını yadda saxlayarkən xəta: {str(e)}")
            return ConversationHandler.END

        # Update user's slides list in context
        user_slides = context.user_data.get('user_slides', [])
        for i, s in enumerate(user_slides):
            if s['id'] == slide['id']:
                user_slides[i]['category'] = category
                break
        context.user_data['user_slides'] = user_slides

        # Update UI with success message and options
        keyboard = [
            [InlineKeyboardButton("🔄 Redaktə etməyə davam edin", callback_data=f"edit_slide_{slide['id']}")],
            [InlineKeyboardButton("🔙 Slaydlara qayıt", callback_data="my_slides")]
        ]
        
        await query.edit_message_text(
            f"✅ Kateqoriya '{category}' olaraq uğurla yeniləndi.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return MY_SLIDES

    except Exception as e:
        logger.error(f"Error in handle_edit_category: {e}")
        # Provide user with error and recovery option
        keyboard = [[InlineKeyboardButton("🔙 Əsas Menyu", callback_data="main_menu")]]
        await query.edit_message_text(
            f"Xəta baş verdi. Zəhmət olmasa yenidən cəhd edin.\nXəta detalları: {str(e)}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ConversationHandler.END

# Helper function to display category selection
async def show_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows category selection buttons"""
    query = update.callback_query
    
    # Define available categories
    categories = [
        ["IT", "Riyaziyyat", "Elektronika"],
        ["English", "Biznes və İdarəetmə", "İqtisadiyyat"],
        ["Dizayn", "Memarlıq", "Neft-Qaz"],
        ["Dilçilik", "Tibb", "Tarix"],
        ["Hüquq", "SƏTƏMM", "Digər"]
    ]
    
    # Create keyboard with categories
    keyboard = []
    for row in categories:
        keyboard.append([InlineKeyboardButton(cat, callback_data=f"edit_category_{cat}") for cat in row])
    
    keyboard.append([InlineKeyboardButton("🔙 Geri", callback_data="edit_slide_back")])
    
    await query.edit_message_text(
        "Yeni kateqoriyanı seçin və ya daxil edin:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return EDIT_CATEGORY

# Helper function to display language selection
async def show_language_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows language selection buttons"""
    query = update.callback_query
    
    # Define available languages
    languages = [
        ["Azərbaycan", "English", "Русский"]
    ]
    
    # Create keyboard with languages
    keyboard = []
    for row in languages:
        keyboard.append([InlineKeyboardButton(lang, callback_data=f"edit_language_{lang}") for lang in row])
    
    keyboard.append([InlineKeyboardButton("🔙 Geri", callback_data="edit_slide_back")])
    
    await query.edit_message_text(
        "Yeni dili seçin:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return EDIT_LANGUAGE

async def handle_edit_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    value = update.message.text.strip()
    field = context.user_data.get('edit_field')
    slide = context.user_data.get('selected_slide')

    if not slide or not field:
        await update.message.reply_text("Xəta: Seçilmiş slayd və ya sahə tapılmadı.")
        return ConversationHandler.END

    try:
        # Value validation based on field type
        if field == "qiymət":
            try:
                value = float(value)
                if value <= 0:
                    raise ValueError("Qiymət sıfırdan böyük olmalıdır.")
            except ValueError:
                await update.message.reply_text("Xəta: Düzgün qiymət daxil edin (məsələn: 5.5)")
                return EDIT_VALUE
                
        elif field == "səhifə sayı":
            try:
                value = int(value)
                if value <= 0:
                    raise ValueError("Səhifə sayı sıfırdan böyük olmalıdır.")
            except ValueError:
                await update.message.reply_text("Xəta: Düzgün səhifə sayı daxil edin (məsələn: 15)")
                return EDIT_VALUE
                
        elif not value:
            raise ValueError("Dəyər boş ola bilməz.")

        # Load all slides
        slides = load_slides()
        
        # Find and update the specific slide
        for i, s in enumerate(slides):
            if s['id'] == slide['id']:
                # Map field names to database fields
                field_mapping = {
                    "ad": "name",
                    "kateqoriya": "category",
                    "qiymət": "price",
                    "dil": "language",
                    "səhifə sayı": "pages",
                    "kart": "card"
                }
                
                # Get the correct database field name
                db_field = field_mapping.get(field, field)
                
                # Update the field
                slides[i][db_field] = value
                
                # Save the updated slides
                with open(DB_FILE, 'w', encoding='utf-8') as f:
                    json.dump(slides, f, indent=2, ensure_ascii=False)
                
                # Update the slide in context
                context.user_data['selected_slide'] = slides[i]
                
                await update.message.reply_text(f"✅ {field.capitalize()} '{value}' olaraq yeniləndi.")
                return await my_slides(update, context)
                
        raise ValueError("Slayd tapılmadı.")

    except ValueError as e:
        await update.message.reply_text(f"Xəta: {str(e)}")
        return EDIT_VALUE
    except Exception as e:
        logger.error(f"Error updating slide field {field}: {e}")
        await update.message.reply_text("Xəta baş verdi. Zəhmət olmasa yenidən cəhd edin.")
        return ConversationHandler.END

async def my_slides(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    logger.info(f"User {user.id} ({user.full_name}) requested their slides")

    slides = load_slides()
    user_slides = [slide for slide in slides if slide['owner'] == user.id]

    if not user_slides:
        await update.message.reply_text("Siz hələ heç bir təqdimat paylaşmamısınız.")
        return ConversationHandler.END

    keyboard = []
    for i, slide in enumerate(user_slides):
        button_text = f"{slide['name']} [Kateqoriya: {slide.get('category', 'Naməlum')}]"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"myslide_{i}")])

    keyboard.append([InlineKeyboardButton("🔙 Əsas Menyu", callback_data="main_menu")])

    await update.message.reply_text(
        f"Sizin {len(user_slides)} təqdimatınız tapıldı:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    context.user_data['user_slides'] = user_slides
    return MY_SLIDES

# Handler for selecting a slide
async def handle_slide_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        index = int(query.data.replace("myslide_", ""))
        user_slides = context.user_data.get('user_slides', [])
        
        if 0 <= index < len(user_slides):
            slide = user_slides[index]
            context.user_data['selected_slide'] = slide
            
            # Format slide info with default values for missing fields
            slide_info = (
                f"📑 Təqdimat məlumatları:\n\n"
                f"Ad: {slide.get('name', 'Məlumat yoxdur')}\n"
                f"Kateqoriya: {slide.get('category', 'Məlumat yoxdur')}\n"
                f"Dil: {slide.get('language', 'Məlumat yoxdur')}\n"
                f"Səhifə sayı: {slide.get('pages', 'Məlumat yoxdur')}\n"
                f"Qiymət: {slide.get('price', 'Məlumat yoxdur')} AZN\n"
                f"Kart: {slide.get('card', 'Məlumat yoxdur')}\n"
                f"Format: {slide.get('file_type', 'Məlumat yoxdur')}\n"
                f"Yüklənmə tarixi: {slide.get('timestamp', 'Məlumat yoxdur')}\n"
                f"Satış sayı: {slide.get('sales', 0)}"
            )
            
            # Show images if available
            if slide.get('images'):
                for image_path in slide['images']:
                    if os.path.exists(image_path):
                        try:
                            await context.bot.send_photo(
                                chat_id=query.message.chat_id,
                                photo=open(image_path, 'rb')
                            )
                        except Exception as e:
                            logger.error(f"Error sending image {image_path}: {e}")
            
            # Create action buttons
            keyboard = [
                [InlineKeyboardButton("✏️ Düzəliş et", callback_data="edit_slide")],
                [InlineKeyboardButton("🗑️ Sil", callback_data="delete_slide")],
                [InlineKeyboardButton("🔙 Geri", callback_data="back_to_slides")]
            ]
            
            await query.message.reply_text(
                slide_info,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return SELECT_SLIDE_ACTION
        
        else:
            await query.message.reply_text("Xəta: Seçilmiş slayd tapılmadı.")
            return ConversationHandler.END
            
    except Exception as e:
        logger.error(f"Error in handle_slide_selection: {e}")
        await query.message.reply_text("Xəta baş verdi. Zəhmət olmasa yenidən cəhd edin.")
        return ConversationHandler.END


# -- Main App 
def main():
    app = Application.builder().token(TOKEN).build()

    os.makedirs("downloads", exist_ok=True)
    os.makedirs("images", exist_ok=True)
    os.makedirs("payments", exist_ok=True)

    if not os.path.exists("pending_uploads.json"):
        with open("pending_uploads.json", 'w', encoding='utf-8') as f:
            json.dump([], f, indent=2, ensure_ascii=False)

    app.add_error_handler(error_handler)

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("mySlides", my_slides),
            CallbackQueryHandler(handle_choice, pattern="^(upload|search)$")
        ],
        states={
            UPLOAD_SLIDE: [MessageHandler(filters.Document.ALL, handle_file)],
            UPLOAD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name)],
            UPLOAD_CATEGORY: [
                CallbackQueryHandler(handle_category, pattern=r'^category_'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_category_text)
            ],
            UPLOAD_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_price)],
            UPLOAD_LANGUAGE: [CallbackQueryHandler(handle_language, pattern=r'^(lang_|back_to_price)')],
            UPLOAD_PAGES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_pages),
                CallbackQueryHandler(handle_pages, pattern=r'^back_to_language$')
            ],
            UPLOAD_CARD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_card),
                CallbackQueryHandler(handle_card)
            ],
            UPLOAD_IMAGE: [
                MessageHandler(filters.PHOTO, handle_image),
                CallbackQueryHandler(handle_image_choice, pattern="^(finish_upload|add_more)$"),
                CallbackQueryHandler(handle_card, pattern=r'^back_to_card$')
            ],
            SEARCH_TYPE: [
                CallbackQueryHandler(handle_search_type, pattern="^(search_by_name|search_by_category|search_by_language)$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search_by_name)
            ],
            SEARCH_LANGUAGE: [
                CallbackQueryHandler(handle_search_by_language, pattern=r'^search_lang_'),
                CallbackQueryHandler(start, pattern="^main_menu$")
            ],
            SEARCH_CATEGORY: [CallbackQueryHandler(handle_search_category, pattern=r'^search_category_')],
            SEARCH_OTHER_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search_other_category)],
            SELECT_SLIDE: [
                CallbackQueryHandler(view_selected_slide, pattern=r'^slide_\d+$'),
                CallbackQueryHandler(start, pattern="^main_menu$")
            ],
            CONFIRM_PAYMENT: [
                CallbackQueryHandler(request_payment, pattern="^buy$"),
                CallbackQueryHandler(back_to_results, pattern="^back_to_results$"),
                MessageHandler(filters.PHOTO, confirm_payment)
            ],
            MY_SLIDES: [
                CallbackQueryHandler(handle_slide_selection, pattern=r'^myslide_\d+$'),
                CallbackQueryHandler(start, pattern="^main_menu$")
            ],
            SELECT_SLIDE_ACTION: [
                CallbackQueryHandler(handle_slide_action, pattern="^(edit_slide|delete_slide|back_to_slides)$")
            ],
            EDIT_FIELD: [
                CallbackQueryHandler(handle_edit_field),
                CallbackQueryHandler(handle_edit_category, pattern=r'^edit_category_\w+'),
                CallbackQueryHandler(handle_edit_language, pattern=r'^edit_language_\w+')
        ],
            EDIT_VALUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit_value)
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start)
        ]
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(approve_payment, pattern=r'^approve_payment_\d+$'))
    app.add_handler(CallbackQueryHandler(reject_payment, pattern=r'^reject_payment_\d+$'))
    app.add_handler(CallbackQueryHandler(approve_upload, pattern=r'^approve_upload_\d+_[0-9a-f-]+$'))
    app.add_handler(CallbackQueryHandler(reject_upload, pattern=r'^reject_upload_\d+_[0-9a-f-]+$'))

    logger.info("Bot işə düşdü...")
    app.run_polling()


if __name__ == '__main__':
    main() 