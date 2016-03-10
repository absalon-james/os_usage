from magic_the_decorating.decorator import Base as BaseDecorator


class _RouterDecorator(BaseDecorator):
    """Callable that alters glance's v2 router.

    Adds the usage endpoint.
    """
    def __init__(self):
        """Calls parent class init and sets signature."""
        super(_RouterDecorator, self).__init__('__glance_router_decorator__')

    def setup_init(self, module, config):
        """Adds the usage api endpoint to routes.

        :param module: Python module containing API class
        :param config: Dict - unused at this point.
        :returns: Modified Module
        """
        import usage
        klass_name = 'API'
        method_name = '__init__'

        klass = getattr(module, klass_name, None)
        if klass is None:
            return module

        old_init = getattr(klass, method_name, None)

        def new_init(api_self, mapper):
            """Wrapper for old_init."""
            old_init(api_self, mapper)

            usage_resource = usage.create_resource()
            mapper.resource("usage", "usages",
                            controller=usage_resource)

        setattr(klass, method_name, new_init)
        return module

    def _decorate(self, module, config):
        """Calls the setup init method."""
        return self.setup_init(module, config)

RouterDecorator = _RouterDecorator()
