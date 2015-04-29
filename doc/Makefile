.PHONY: clean-doc doc-html

SPHINXBUILD  = sphinx-build
DOC_BUILDDIR = _build
SPHINXOPTS   = -d $(DOC_BUILDDIR)/doctrees .

help:
	@echo 'Build directives (can be overridden by environment variables'
	@echo 'or by command line parameters):'
	@echo '  DOC_BUILDDIR:       $(DOC_BUILDDIR)'
	@echo
	@echo 'Available targets:'
	@echo '  doc-html  - build html documentation based on source code of product'
	@echo '  clean-doc - clean generated docs'
	@echo



doc-html:
	$(SPHINXBUILD) -b html $(SPHINXOPTS) $(DOC_BUILDDIR)/html
	@echo
	@echo "Build finished. The HTML pages are in $(DOC_BUILDDIR)/html."

clean-doc:
	$ rm -rf  $(DOC_BUILDDIR)
	@echo
	@echo "We are cleaned documentation output."
