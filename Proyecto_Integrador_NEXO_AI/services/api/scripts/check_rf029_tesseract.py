"""Test real de OCR local: requiere Pillow, pytesseract y Tesseract instalado.
No usa ni modifica Neon. Muestra una muestra sintética, no datos privados.
"""
import io
from PIL import Image,ImageDraw,ImageFont
from app.modules.extensions.ocr import recognize

def main():
    image=Image.new('RGB',(950,220),'white');draw=ImageDraw.Draw(image)
    font=None
    for path in (r'C:\Windows\Fonts\arial.ttf','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'):
        try:font=ImageFont.truetype(path,40);break
        except OSError:pass
    draw.text((22,32),'FACTURA DE PRUEBA',fill='black',font=font)
    draw.text((22,111),'TOTAL $ 120.50',fill='black',font=font)
    image_bytes=io.BytesIO();image.save(image_bytes,format='PNG')
    result=recognize(image_bytes.getvalue())
    assert result['raw_text'] and result['confidence']>0
    assert result['suggested_fields']['amount_mxn']=='120.50',result
    print('RF-029 OCR REAL OK: texto y monto reconocidos por Tesseract, sin escrituras en Neon.')

if __name__=='__main__':main()
