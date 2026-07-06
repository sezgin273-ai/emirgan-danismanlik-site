# Emirgan Danışmanlık Ticaret A.Ş. — Kurumsal Web Sitesi

Emirgan Danışmanlık Ticaret Anonim Şirketi için sıfırdan geliştirilen kurumsal web sitesi projesi.

## Gereksinimler

- PHP 8.1 veya üzeri (yerleşik geliştirme sunucusu için)
- Git

## Kurulum

1. Depoyu klonlayın:

   ```bash
   git clone https://github.com/sezgin273-ai/emirgan-danismanlik-site.git
   cd emirgan-danismanlik-site
   ```

2. İçerik dosyası `content/content.json` konumundadır; site metinleri bu dosyadan okunur.

3. Üretim ortamında `public_html/config.php` oluşturulabilir (bu dosya `.gitignore` ile hariç tutulur).

## Yerel Geliştirme Sunucusu

Proje kök dizininden:

```bash
php -S localhost:8080 -t public_html
```

Tarayıcıda [http://localhost:8080](http://localhost:8080) adresini açın.

### PHP kurulu değilse (Windows)

```powershell
winget install PHP.PHP.8.3
```

Kurulumdan sonra terminali yeniden açın ve `php --version` ile doğrulayın.

## Proje Yapısı

```
├── content/
│   └── content.json          # Tüm site içeriği (JSON)
├── docs/                     # Kaynak belgeler (PDF, DOCX)
├── public_html/              # Web kök dizini
│   ├── index.php
│   ├── kvkk.php
│   ├── admin/
│   ├── api/
│   │   └── contact.php
│   ├── assets/
│   │   ├── css/
│   │   ├── img/
│   │   └── js/
│   └── includes/
└── README.md
```

## Lisans

© Emirgan Danışmanlık Ticaret Anonim Şirketi
