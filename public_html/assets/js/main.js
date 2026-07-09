(function () {
  'use strict';

  document.documentElement.classList.add('js');

  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const showReveal = (el) => {
    el.classList.add('is-visible');
  };

  const initReveal = () => {
    const revealEls = document.querySelectorAll('.reveal');
    if (revealEls.length === 0) {
      return;
    }

    if (prefersReducedMotion || !('IntersectionObserver' in window)) {
      revealEls.forEach(showReveal);
      return;
    }

    const revealObserver = new IntersectionObserver(
      (entries, observer) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            showReveal(entry.target);
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.01, rootMargin: '0px 0px 0px 0px' }
    );

    revealEls.forEach((el) => {
      revealObserver.observe(el);
    });

    // Güvenlik: layout tamamlandıktan sonra görünür alandakileri hemen göster
    requestAnimationFrame(() => {
      revealEls.forEach((el) => {
        const rect = el.getBoundingClientRect();
        if (rect.top < window.innerHeight && rect.bottom > 0) {
          showReveal(el);
        }
      });
    });
  };

  const initServiceStagger = () => {
    const cards = document.querySelectorAll('.service-card[data-stagger-index]');
    if (cards.length === 0) {
      return;
    }

    const revealCard = (card, index) => {
      card.style.setProperty('--stagger-delay', `${index * 70}ms`);
      card.classList.add('is-visible');
    };

    if (prefersReducedMotion || !('IntersectionObserver' in window)) {
      cards.forEach((card) => {
        revealCard(card, parseInt(card.getAttribute('data-stagger-index') || '0', 10));
      });
      return;
    }

    document.documentElement.classList.add('js-service-stagger');

    const staggerObserver = new IntersectionObserver(
      (entries, observer) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) {
            return;
          }
          const card = entry.target;
          const index = parseInt(card.getAttribute('data-stagger-index') || '0', 10);
          revealCard(card, index);
          observer.unobserve(card);
        });
      },
      { threshold: 0.08, rootMargin: '0px 0px -4% 0px' }
    );

    cards.forEach((card) => {
      staggerObserver.observe(card);
    });

    requestAnimationFrame(() => {
      cards.forEach((card) => {
        const rect = card.getBoundingClientRect();
        if (rect.top < window.innerHeight && rect.bottom > 0) {
          const index = parseInt(card.getAttribute('data-stagger-index') || '0', 10);
          revealCard(card, index);
        }
      });
    });
  };

  const boot = () => {
    initReveal();
    initServiceStagger();
    // Son çare: gizli kalan reveal öğelerini 1 sn sonra göster
    window.setTimeout(() => {
      document.querySelectorAll('.reveal:not(.is-visible)').forEach(showReveal);
    }, 1000);
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

  /* -----------------------------------------------------------------------
     Mobile navigation
     ----------------------------------------------------------------------- */
  const navToggle = document.querySelector('[data-nav-toggle]');
  const siteNav = document.getElementById('site-nav');
  const navToggleLabel = document.querySelector('[data-nav-toggle-label]');

  if (navToggle && siteNav) {
    const openLabel = navToggleLabel ? navToggleLabel.textContent : '';
    const closeLabel = navToggle.getAttribute('data-close-label') || openLabel;

    navToggle.addEventListener('click', () => {
      const isOpen = siteNav.classList.toggle('is-open');
      navToggle.setAttribute('aria-expanded', String(isOpen));
      if (navToggleLabel) {
        navToggleLabel.textContent = isOpen ? closeLabel : openLabel;
      }
    });

    siteNav.querySelectorAll('a').forEach((link) => {
      link.addEventListener('click', () => {
        siteNav.classList.remove('is-open');
        navToggle.setAttribute('aria-expanded', 'false');
        if (navToggleLabel) {
          navToggleLabel.textContent = openLabel;
        }
      });
    });
  }

  /* -----------------------------------------------------------------------
     Header scroll state
     ----------------------------------------------------------------------- */
  const header = document.getElementById('site-header');

  if (header) {
    const onScroll = () => {
      header.classList.toggle('is-scrolled', window.scrollY > 8);
    };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
  }

  /* -----------------------------------------------------------------------
     Active section highlighting
     ----------------------------------------------------------------------- */
  const navLinks = document.querySelectorAll('[data-nav-link]');
  const sections = [];

  navLinks.forEach((link) => {
    const id = link.getAttribute('data-nav-link');
    const section = document.getElementById(id);
    if (section) {
      sections.push({ id, el: section, link });
    }
  });

  if (sections.length > 0 && 'IntersectionObserver' in window) {
    const sectionObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            const id = entry.target.id;
            navLinks.forEach((link) => {
              link.classList.toggle(
                'is-active',
                link.getAttribute('data-nav-link') === id
              );
            });
          }
        });
      },
      {
        rootMargin: '-40% 0px -50% 0px',
        threshold: 0,
      }
    );

    sections.forEach(({ el }) => sectionObserver.observe(el));
  }

  /* -----------------------------------------------------------------------
     Contact form — client-side validation only
     ----------------------------------------------------------------------- */
  const contactForm = document.getElementById('contact-form');
  const formFeedback = document.getElementById('form-feedback');

  if (contactForm && formFeedback) {
    const successMessage = contactForm.getAttribute('data-success') || '';
    const errorMessage = contactForm.getAttribute('data-error') || '';

    const showFeedback = (message, type) => {
      formFeedback.textContent = message;
      formFeedback.hidden = false;
      formFeedback.className = 'form-feedback is-' + type;
    };

    const clearInvalid = () => {
      contactForm.querySelectorAll('.is-invalid').forEach((el) => {
        el.classList.remove('is-invalid');
      });
    };

    const validateForm = () => {
      clearInvalid();

      const name = contactForm.querySelector('#contact-name');
      const email = contactForm.querySelector('#contact-email');
      const subject = contactForm.querySelector('#contact-subject');
      const message = contactForm.querySelector('#contact-message');

      let valid = true;

      [name, email, subject, message].forEach((field) => {
        if (!field || !field.value.trim()) {
          if (field) {
            field.classList.add('is-invalid');
          }
          valid = false;
        }
      });

      if (email && email.value && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.value)) {
        email.classList.add('is-invalid');
        valid = false;
      }

      return valid;
    };

    contactForm.addEventListener('submit', (event) => {
      if (!document.documentElement.classList.contains('js')) {
        return;
      }

      event.preventDefault();
      formFeedback.hidden = true;

      if (!validateForm()) {
        showFeedback(errorMessage, 'error');
        return;
      }

      const submitBtn = contactForm.querySelector('button[type="submit"]');
      if (submitBtn) {
        submitBtn.disabled = true;
      }

      fetch('/api/contact.php', {
        method: 'POST',
        headers: { Accept: 'application/json' },
        body: new FormData(contactForm),
      })
        .then((response) => {
          return response.json().then((data) => ({ response, data }));
        })
        .then(({ response, data }) => {
          if (response.ok && data.ok) {
            showFeedback(data.message || successMessage, 'success');
            contactForm.reset();
            return;
          }
          showFeedback(data.message || errorMessage, 'error');
        })
        .catch(() => {
          showFeedback(errorMessage, 'error');
        })
        .finally(() => {
          if (submitBtn) {
            submitBtn.disabled = false;
          }
        });
    });
  }
})();
