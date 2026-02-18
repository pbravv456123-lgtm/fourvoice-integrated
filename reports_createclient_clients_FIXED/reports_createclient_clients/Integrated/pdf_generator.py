"""
PDF Invoice Generator
Creates professional PDF invoices for clients
"""

import os
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from io import BytesIO
from datetime import datetime

def generate_invoice_pdf(invoice_data):
    """
    Generate a professional PDF invoice
    
    Args:
        invoice_data (dict): Invoice data containing:
            - invoice_number: Invoice number
            - client_name: Client name
            - email: Client email
            - address: Client address
            - sent_date: Invoice date (YYYY-MM-DD format)
            - due_date: Due date (YYYY-MM-DD format)
            - subtotal: Subtotal amount
            - tax: Tax amount
            - total: Total amount
            - items: List of invoice items with description, qty, rate, amount
            - notes: Invoice notes (optional)
    
    Returns:
        BytesIO: PDF file as bytes for embedding or downloading
    """
    
    # Create PDF in memory
    pdf_buffer = BytesIO()
    doc = SimpleDocTemplate(pdf_buffer, pagesize=letter,
                           rightMargin=0.5*inch, leftMargin=0.5*inch,
                           topMargin=0.75*inch, bottomMargin=0.5*inch)
    
    # Container for PDF elements
    elements = []
    
    # Define styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#2c3e50'),
        spaceAfter=6,
        alignment=TA_LEFT,
        fontName='Helvetica-Bold'
    )
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=11,
        textColor=colors.HexColor('#2c3e50'),
        spaceAfter=8,
        alignment=TA_LEFT,
        fontName='Helvetica-Bold'
    )
    label_style = ParagraphStyle(
        'CustomLabel',
        parent=styles['Normal'],
        fontSize=12,
        textColor=colors.HexColor('#2c3e50'),
        alignment=TA_LEFT
    )
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.HexColor('#2c3e50'),
        alignment=TA_LEFT
    )
    
    # Header - Company name, sender info, and Invoice title
    sender_email = invoice_data.get('sender_email', os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@company.com'))
    sender_phone = invoice_data.get('sender_phone', '+65 9123 4567')
    
    company_info = f'''<b>FourVoice</b><br/>
    <font size="10">Sender Email: {sender_email}</font><br/>
    <font size="10">Sender Phone: {sender_phone}</font>'''
    
    header_data = [
        [Paragraph(company_info, ParagraphStyle('', parent=styles['Normal'], fontSize=24, textColor=colors.HexColor('#2c3e50'), fontName='Helvetica-Bold')),
         Paragraph('<b>INVOICE</b>', ParagraphStyle('', parent=styles['Normal'], fontSize=20, textColor=colors.HexColor('#e74c3c'), fontName='Helvetica-Bold', alignment=TA_RIGHT))]
    ]
    header_table = Table(header_data, colWidths=[3.5*inch, 3.5*inch])
    header_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('VALIGN', (0, 0), (0, -1), 'TOP'),
        ('VALIGN', (1, 0), (1, 0), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 20),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 0.05*inch))
    
    # Invoice details - 3-column row with labels and values stacked vertically
    invoice_number = invoice_data.get('invoice_number', 'N/A')
    sent_date = invoice_data.get('sent_date', 'N/A')
    due_date = invoice_data.get('due_date', 'N/A')

    detail_label_style = ParagraphStyle(
        'DetailLabel',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.HexColor('#34495e'),
        fontName='Helvetica-Bold',
        spaceAfter=2
    )
    detail_value_style = ParagraphStyle(
        'DetailValue',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.HexColor('#2c3e50')
    )

    col1_text = f'''<b>Invoice #:</b><br/>{str(invoice_number)}'''
    col2_text = f'''<b>Invoice Date:</b><br/>{str(sent_date)}'''
    col3_text = f'''<b>Due Date:</b><br/>{str(due_date)}'''
    
    details_data = [[
        Paragraph(col1_text, ParagraphStyle('', parent=detail_value_style, fontSize=11)),
        Paragraph(col2_text, ParagraphStyle('', parent=detail_value_style, fontSize=11)),
        Paragraph(col3_text, ParagraphStyle('', parent=detail_value_style, fontSize=11))
    ]]
    
    details_table = Table(details_data, colWidths=[2.33*inch, 2.33*inch, 2.33*inch])
    details_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    elements.append(details_table)
    elements.append(Spacer(1, 0.15*inch))
    
    # Bill To section
    bill_to_heading = ParagraphStyle(
        'BillToHeading',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.HexColor('#2c3e50'),
        fontName='Helvetica-Bold',
        spaceAfter=8
    )
    bill_to_style = ParagraphStyle(
        'BillTo',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.HexColor('#2c3e50'),
        leading=14
    )
    
    elements.append(Paragraph('<b>BILL TO:</b>', bill_to_heading))
    client_name = invoice_data.get('client_name', 'Valued Client')
    email = invoice_data.get('email', 'N/A')
    address = invoice_data.get('address', 'N/A')
    
    bill_to_text = f'''<b>{client_name}</b><br/>
    {email}<br/>
    {address}'''
    
    elements.append(Paragraph(bill_to_text, bill_to_style))
    elements.append(Spacer(1, 0.2*inch))
    
    # Line items table
    items = invoice_data.get('items', [])
    items_data = [['Description', 'Qty', 'Rate', 'Amount']]
    
    for item in items:
        description = item.get('description', 'Service')
        qty = item.get('qty', 1)
        rate = item.get('rate', '$0.00')
        amount = item.get('amount', '$0.00')
        
        items_data.append([
            Paragraph(description, normal_style),
            Paragraph(str(qty), ParagraphStyle('', parent=normal_style, alignment=TA_CENTER)),
            Paragraph(str(rate), ParagraphStyle('', parent=normal_style, alignment=TA_RIGHT)),
            Paragraph(str(amount), ParagraphStyle('', parent=normal_style, alignment=TA_RIGHT))
        ])
    
    items_table = Table(items_data, colWidths=[3.5*inch, 0.8*inch, 1.3*inch, 1.4*inch])
    items_table.setStyle(TableStyle([
        # Header row
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ecf0f1')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 11),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        # Data rows
        ('FONT', (0, 1), (-1, -1), 'Helvetica', 11),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#2c3e50')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#bdc3c7')),
    ]))
    elements.append(items_table)
    elements.append(Spacer(1, 0.2*inch))
    
    # Totals section - right aligned
    subtotal = invoice_data.get('subtotal', '$0.00')
    tax = invoice_data.get('tax', '$0.00')
    total = invoice_data.get('total', '$0.00')
    
    totals_data = [
        ['Subtotal:', subtotal],
        ['Tax (9% GST):', tax],
        ['Total:', total]
    ]
    totals_table = Table(totals_data, colWidths=[5.4*inch, 1.6*inch])
    totals_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONT', (0, 0), (0, 1), 'Helvetica', 12),
        ('FONT', (1, 0), (1, 1), 'Helvetica', 12),
        ('TEXTCOLOR', (0, 0), (1, 1), colors.HexColor('#2c3e50')),
        ('BOTTOMPADDING', (0, 0), (-1, 1), 6),
        ('TOPPADDING', (0, 0), (-1, 1), 6),
        ('LINEBELOW', (0, 1), (-1, 1), 0.5, colors.HexColor('#ecf0f1')),
        # Total row - bold and underline
        ('FONT', (0, 2), (-1, 2), 'Helvetica-Bold', 13),
        ('TEXTCOLOR', (0, 2), (-1, 2), colors.HexColor('#2c3e50')),
        ('BOTTOMPADDING', (0, 2), (-1, 2), 8),
        ('TOPPADDING', (0, 2), (-1, 2), 8),
        ('LINEBELOW', (0, 2), (-1, 2), 1, colors.HexColor('#2c3e50')),
    ]))
    elements.append(totals_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Notes section if provided
    notes = invoice_data.get('notes', '')
    if notes:
        elements.append(Paragraph('<b>Notes:</b>', heading_style))
        elements.append(Paragraph(notes, normal_style))
        elements.append(Spacer(1, 0.2*inch))
    
    # Footer
    elements.append(Spacer(1, 0.1*inch))
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#95a5a6'),
        alignment=TA_CENTER
    )
    elements.append(Paragraph('Thank you for your business!', footer_style))
    elements.append(Paragraph('FourVoice - Professional Invoice Management', footer_style))
    elements.append(Paragraph('This invoice was automatically generated.', footer_style))
    
    # Build PDF
    doc.build(elements)
    pdf_buffer.seek(0)
    return pdf_buffer
